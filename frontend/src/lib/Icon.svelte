<script lang="ts">
  let { name, size = 20 }: {name: string; size?: number} = $props();
  const paths: Record<string, string> = {
    grid: 'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
    server: 'M4 3h16v7H4z M4 14h16v7H4z M7 6.5h.01 M7 17.5h.01 M11 6.5h6 M11 17.5h6',
    box: 'M12 3 3 8v9l9 5 9-5V8z M3 8l9 5 9-5 M12 13v9 M7 5.8l10 5.6',
    activity: 'M2 12h5l3-9 4 18 3-9h5',
    terminal: 'm4 6 5 6-5 6 M12 18h8',
    git: 'M6 3v12a4 4 0 0 0 4 4h5 M18 6v5a4 4 0 0 1-4 4H6 M3 3a3 3 0 1 0 6 0a3 3 0 1 0-6 0 M15 3a3 3 0 1 0 6 0a3 3 0 1 0-6 0 M15 19a3 3 0 1 0 6 0a3 3 0 1 0-6 0',
    heart: 'M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8Z',
    settings: 'M12 8a4 4 0 1 0 0 8a4 4 0 1 0 0-8 M9 3h6l1 3 3 1 2 5-2 5-3 1-1 3H9l-1-3-3-1-2-5 2-5 3-1z',
    arrow: 'M7 17 17 7 M7 7h10v10',
    plus: 'M12 5v14 M5 12h14',
    refresh: 'M20 7v5h-5 M4 17v-5h5 M6 6a8 8 0 0 1 14 6 M4 12a8 8 0 0 0 14 6',
    chevron: 'm9 5 7 7-7 7',
    cpu: 'M7 7h10v10H7z M10 10h4v4h-4z M9 3v4 M15 3v4 M9 17v4 M15 17v4 M3 9h4 M3 15h4 M17 9h4 M17 15h4',
    memory: 'M3 6h18v12H3z M7 10v4 M11 10v4 M15 10v4 M19 18v3 M15 18v3 M11 18v3 M7 18v3',
    disk: 'M5 3h14l3 13v5H2v-5z M2 16h20 M17 18.5h2',
    network: 'M12 3v7 M5 17v-5h14v5 M2 17h6v5H2z M9 1h6v5H9z M16 17h6v5h-6z',
    moon: 'M21 13A9 9 0 0 1 11 3a9 9 0 1 0 10 10Z',
    sun: 'M12 8a4 4 0 1 0 0 8a4 4 0 1 0 0-8 M12 1v3 M12 20v3 M1 12h3 M20 12h3 M4 4l2 2 M18 18l2 2 M4 20l2-2 M18 6l2-2',
    logout: 'M9 3H3v18h6 M9 12h12 M16 7l5 5-5 5',
    search: 'M10 3a7 7 0 1 0 0 14a7 7 0 1 0 0-14 M15 15l6 6',
    shield: 'M12 2 3 6v6c0 6 9 10 9 10s9-4 9-10V6z m-5 10 3 3 6-6',
    check: 'm5 12 4 4L19 6',
    close: 'm6 6 12 12 M6 18 18 6',
    download: 'M12 3v12 m-5-5 5 5 5-5 M4 16v5h16v-5',
    clock: 'M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18 M12 7v5l3 2',
    alert: 'm12 3 10 18H2z M12 9v5 M12 17h.01',
    edit: 'm16 3 5 5-12 12-6 1 1-6z M14 5l5 5',
    lock: 'M5 10h14v11H5z M8 10V6a4 4 0 0 1 8 0v4',
  };
</script>

<svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d={paths[name] || paths.server}/></svg>
