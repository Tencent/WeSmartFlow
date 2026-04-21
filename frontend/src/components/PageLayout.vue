<template>
  <div class="page-layout" :class="{ 'page-layout--full': full }">
    <!-- Page header -->
    <div v-if="title || $slots.actions" class="pl-header">
      <div class="pl-title-group">
        <h1 class="pl-title">
          <span v-if="icon" class="pl-icon">{{ icon }}</span>
          {{ title }}
          <slot name="title-badge" />
        </h1>
        <p v-if="$slots.subtitle || subtitle" class="pl-subtitle">
          <slot name="subtitle">
            {{ subtitle }}
          </slot>
        </p>
      </div>
      <div v-if="$slots.actions" class="pl-actions">
        <slot name="actions" />
      </div>
    </div>

    <!-- Optional sub-header (tabs, filters, stats bar etc.) -->
    <div v-if="$slots.subheader" class="pl-subheader">
      <slot name="subheader" />
    </div>

    <!-- Main content -->
    <div class="pl-body" :class="{ 'pl-body--stretch': stretch }">
      <slot />
    </div>
  </div>
</template>

<script setup>
defineProps({
  title: { type: String, default: "" },
  subtitle: { type: String, default: "" },
  icon: { type: String, default: "" },
  // full height layout (KnowledgeBase etc.)
  full: { type: Boolean, default: false },
  // body fills remaining height
  stretch: { type: Boolean, default: false },
});
</script>

<style scoped>
.page-layout {
  padding: 28px 32px;
  max-width: 1200px;
  box-sizing: border-box;
}

/* Full-height variant: fills the whole scroll container */
.page-layout--full {
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* ── Header ────────────────────────────────────────── */
.pl-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 20px;
  flex-shrink: 0;
}

.pl-title-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.pl-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.5px;
  margin: 0;
  line-height: 1.2;
}

.pl-icon {
  font-size: 20px;
  line-height: 1;
}

.pl-subtitle {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0;
  line-height: 1.5;
}

.pl-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

/* ── Sub-header ────────────────────────────────────── */
.pl-subheader {
  margin-bottom: 16px;
  flex-shrink: 0;
}

/* ── Body ──────────────────────────────────────────── */
.pl-body {
  /* default: normal flow */
}

.pl-body--stretch {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
</style>
