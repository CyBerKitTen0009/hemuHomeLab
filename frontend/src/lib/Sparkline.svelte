<script lang="ts">
  let { values = [], color = 'var(--accent)', height = 50, filled = false }: { values?: number[]; color?: string; height?: number; filled?: boolean } = $props();
  const width = 260;
  let points = $derived(values.length < 2 ? '' : values.map((value, i) => `${i / (values.length - 1) * width},${height - 5 - Math.max(0, Math.min(100, value)) / 100 * (height - 10)}`).join(' '));
</script>

<svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" class="sparkline" role="img" aria-label={values.length < 2 ? '等待更多采样数据' : '资源使用趋势'}>
  {#if points}
    {#if filled}<polygon points={`0,${height} ${points} ${width},${height}`} fill={color} opacity="0.07" />{/if}
    <polyline {points} fill="none" stroke={color} stroke-width="2" vector-effect="non-scaling-stroke" stroke-linejoin="round" />
  {:else}<line x1="0" y1={height - 8} x2={width} y2={height - 8} stroke={color} opacity="0.25" stroke-dasharray="4 4" />{/if}
</svg>
