"""图像生成工厂"未配置即失败"守卫的回归测试（issue #62）。

未配置（用户设置与环境变量均为空/缺失）时：
- `get_image_gen` 应在构造期抛 ValueError，而不是把注定失败的客户端交给
  Agent 在运行时报错；
- `build_image_gen_tool` 随之抛 ValueError，`tool_catalog.build_plans` 与
  `generate_html_card` 的既有 except 分支因此生效（不注册图片工具）；
- `generate_card._build_card_writer_agent` 捕获后降级为无图模式。
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _no_user_settings(_user_id: str, _key: str):
    """模拟用户未在设置页自配任何 img_*。"""
    return None


_EMPTY_ENV = {"IMG_API_KEY": "", "IMG_BASE_URL": "", "IMG_MODEL": ""}
_OK_ENV = {
    "IMG_API_KEY": "sk-test",
    "IMG_BASE_URL": "https://example.com/v1",
    "IMG_PROVIDER": "openai",
}


class UnconfiguredImageFactoryTests(unittest.TestCase):
    def test_empty_env_raises(self):
        from services.image_factory import get_image_gen

        with patch.dict(os.environ, _EMPTY_ENV), patch(
            "database.get_setting", _no_user_settings
        ):
            with self.assertRaises(ValueError):
                get_image_gen("u_test", scene="media", with_quota=False)

    def test_missing_env_raises(self):
        """env 变量完全缺失（而非空串）时同样守卫，不再落到遗留默认值。"""
        from services.image_factory import get_image_gen

        with patch.dict(os.environ, {}):
            os.environ.pop("IMG_API_KEY", None)
            os.environ.pop("IMG_BASE_URL", None)
            with patch("database.get_setting", _no_user_settings):
                with self.assertRaises(ValueError):
                    get_image_gen("u_test", scene="media", with_quota=False)

    def test_user_setting_beats_env(self):
        """用户自配的 key/base_url 优先于 env，正常返回客户端。"""
        from services.image_factory import get_image_gen

        with patch.dict(os.environ, _EMPTY_ENV), patch(
            "database.get_setting",
            lambda _u, k: "https://example.com/v1"
            if k == "img_base_url"
            else ("sk-user" if k == "img_api_key" else None),
        ):
            client = get_image_gen("u_test", scene="media", with_quota=False)
            self.assertEqual(client.api_key, "sk-user")

    def test_configured_env_returns_client(self):
        from agent_core.tool.imagegen.openai import OpenAIImageGen

        from services.image_factory import get_image_gen

        with patch.dict(os.environ, _OK_ENV), patch(
            "database.get_setting", _no_user_settings
        ):
            client = get_image_gen("u_test", scene="media", with_quota=False)
            self.assertIsInstance(client, OpenAIImageGen)

    def test_build_image_gen_tool_raises_when_unconfigured(self):
        from agents.tools.image_gen_factory import build_image_gen_tool

        with patch.dict(os.environ, _EMPTY_ENV), patch(
            "database.get_setting", _no_user_settings
        ):
            with self.assertRaises(ValueError):
                build_image_gen_tool("u_test")


class CardWriterDegradationTests(unittest.TestCase):
    def test_card_writer_agent_degrades_without_image_tool(self):
        """generate_card 的裸调用已补降级：构造不崩、不注册图片工具、prompt 有指引。"""
        from agents.tools import generate_card

        with patch.dict(os.environ, _EMPTY_ENV), patch(
            "database.get_setting", _no_user_settings
        ), patch.object(
            generate_card, "build_image_gen_tool", side_effect=ValueError("未配置")
        ):
            with tempfile.TemporaryDirectory() as tmp:
                agent = generate_card._build_card_writer_agent(Path(tmp), "u_test")

        self.assertIsNone(agent.tool_registry.get("qwen_image_generate"))
        prompt = agent.prompt_builder.build_system_prompt()
        self.assertIn("当前没有可用的图片工具", prompt)
        self.assertTrue(
            prompt.startswith(generate_card._CARD_WRITER_SYSTEM_PROMPT),
            "降级提示应追加在原 prompt 之后，原 prompt 保持完整",
        )


if __name__ == "__main__":
    unittest.main()
