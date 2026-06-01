/**
 * EduViz 交互式可视化组件
 *
 * 使用方式：
 * <EduVizSandbox
 *   title="导数的几何意义"
 *   description="拖动滑块观察割线如何趋近切线"
 *   :code="agentGeneratedCode"
 *   @ready="onReady"
 *   @error="onError"
 *   @event="onEvent"
 * />
 */
export { default as EduVizSandbox } from "./EduVizSandbox.vue";
