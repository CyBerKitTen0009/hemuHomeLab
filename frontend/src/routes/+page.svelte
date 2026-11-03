<script lang="ts">
  import { onMount } from 'svelte';
  import Icon from '../lib/Icon.svelte';
  import Sparkline from '../lib/Sparkline.svelte';
  import { api, ApiError, setCsrf } from '../lib/api';
  import type { Audit, Device, DeviceConfig, Sample } from '../lib/types';

  type Page = 'overview' | 'devices' | 'docker' | 'systemd' | 'git' | 'logs' | 'health' | 'settings';
  const navigation: {id: Page; label: string; icon: string}[] = [
    {id:'overview',label:'总览',icon:'grid'}, {id:'devices',label:'设备',icon:'server'},
    {id:'docker',label:'Docker',icon:'box'}, {id:'systemd',label:'系统服务',icon:'activity'},
    {id:'git',label:'Git 项目',icon:'git'}, {id:'logs',label:'日志中心',icon:'terminal'},
    {id:'health',label:'健康检查',icon:'heart'}, {id:'settings',label:'设置与审计',icon:'settings'}
  ];
  const titles: Record<Page, string> = {overview:'你的 Homelab，尽在掌握。',devices:'每一台设备，都有迹可循。',docker:'容器与工作负载。',systemd:'系统服务的运行脉搏。',git:'代码，和它所在的地方。',logs:'把线索连起来。',health:'服务现在还好吗？',settings:'让控制台按你的方式运行。'};
  let page = $state<Page>('overview');
  let authenticated = $state(false);
  let starting = $state(true);
  let username = $state('admin');
  let password = $state('');
  let loginError = $state('');
  let busy = $state(false);
  let devices = $state<Device[]>([]);
  let selectedId = $state('');
  let history = $state<Sample[]>([]);
  let audits = $state<Audit[]>([]);
  let search = $state('');
  let dark = $state(true);
  let mobileNav = $state(false);
  let toast = $state('');
  let toastError = $state(false);
  let sshEnabled = $state(false);
  let pollSeconds = $state(30);
  let metricTab = $state<'cpu_percent' | 'memory_percent' | 'disk_percent'>('cpu_percent');
  let dockerTab = $state<'containers' | 'images' | 'compose'>('containers');
  let logSource = $state('system');
  let logTarget = $state('');
  let logSearch = $state('');
  let logLevel = $state('all');
  let logLines = $state<string[]>([]);
  let logLoading = $state(false);
  let logError = $state('');
  let logRequest = 0;
  let searchInput = $state<HTMLInputElement>();
  let deviceDialog: HTMLDialogElement;
  let confirmDialog: HTMLDialogElement;
  let restoreInput = $state<HTMLInputElement>();
  let confirmTitle = $state('');
  let confirmText = $state('');
  let confirmAction: () => Promise<void> = async () => {};
  let editId = $state('');
  let form = $state<DeviceConfig>(emptyForm());
  let gitPaths = $state('');
  let healthTargets = $state('');
  let formError = $state('');
  let timer: ReturnType<typeof setTimeout>;

  let selected = $derived(devices.find(device => device.id === selectedId) || devices[0]);
  let snapshot = $derived(selected?.snapshot);
  let metrics = $derived(snapshot?.metrics);
  let online = $derived(devices.filter(device => device.snapshot?.status === 'online'));
  let containers = $derived(snapshot?.docker?.containers || []);
  let services = $derived(snapshot?.systemd?.services || []);
  let repos = $derived(snapshot?.git || []);
  let checks = $derived(snapshot?.health || []);
  let runningCount = $derived(devices.reduce((sum, device) => sum + (device.snapshot?.status === 'online' ? device.snapshot?.docker?.containers.filter(item => item.state === 'running').length || 0 : 0), 0));
  let issueCount = $derived(devices.reduce((sum, device) => sum + (device.snapshot?.status === 'error' ? 1 : 0) + (device.snapshot?.systemd?.services.filter(item => item.active === 'failed').length || 0), 0));
  let visibleLines = $derived(logLines.filter(line => (logLevel === 'all' || line.toLowerCase().includes(logLevel)) && line.toLowerCase().includes(logSearch.toLowerCase())));

  function emptyForm(): DeviceConfig { return {name:'',host:'hemu-server.top',port:22,username:'',mode:'ssh',credential_ref:'thinkbook',jump_device_id:null,kind:'linux',git_paths:[],health_targets:[]}; }
  function bytes(value: number = 0) { if (value < 1024) return `${Math.round(value)} B`; const i = Math.min(4, Math.floor(Math.log(value) / Math.log(1024))); return `${(value / 1024 ** i).toFixed(i >= 2 ? 1 : 0)} ${['B','KiB','MiB','GiB','TiB'][i]}`; }
  function date(value?: number) { return value ? new Date(value * 1000).toLocaleTimeString('zh-CN', {hour:'2-digit',minute:'2-digit',second:'2-digit'}) : '尚未采集'; }
  function uptime(value = 0) { return `${Math.floor(value / 86400)} 天 ${Math.floor(value % 86400 / 3600)} 小时`; }
  function matches(...values: (string | undefined)[]) { return !search || values.join(' ').toLowerCase().includes(search.toLowerCase()); }
  function statusName(status?: string) { return status === 'online' ? '在线' : status === 'error' ? '连接异常' : status === 'offline' ? '离线' : '等待采集'; }
  function notify(message: string, error = false) { toast = message; toastError = error; clearTimeout(timer); timer = setTimeout(() => toast = '', 5500); }
  function handleError(error: unknown) { if (error instanceof ApiError && error.status === 401) authenticated = false; notify(error instanceof Error ? error.message : '请求失败', true); }
  function navigate(next: Page) { page = next; search = ''; mobileNav = false; location.hash = next; if (next === 'settings') void loadAudits(); }
  function setTheme() { dark = !dark; document.documentElement.dataset.theme = dark ? 'dark' : 'light'; localStorage.setItem('hcc-theme', dark ? 'dark' : 'light'); }

  async function loadHistory() {
    if (!selected) { history = []; return; }
    const id = selected.id;
    try { const result = await api<Sample[]>(`/devices/${id}/history`); if (selected?.id === id) history = result; } catch (error) { handleError(error); }
  }
  async function loadDevices() {
    try { devices = await api<Device[]>('/devices'); if (!devices.some(item => item.id === selectedId)) selectedId = devices[0]?.id || ''; await loadHistory(); } catch (error) { handleError(error); }
  }
  async function loadAudits() { try { audits = await api<Audit[]>('/audit'); } catch (error) { handleError(error); } }
  async function selectDevice(id: string) { selectedId = id; history = []; logLines = []; logError = ''; logRequest++; logLoading = false; logTarget = ''; await loadHistory(); }
  async function login(event: SubmitEvent) {
    event.preventDefault(); busy = true; loginError = '';
    try { const result = await api<{csrf_token: string}>('/login', 'POST', {username, password}); setCsrf(result.csrf_token); password = ''; authenticated = true; await boot(); }
    catch (error) { loginError = error instanceof Error ? error.message : '登录失败'; }
    finally { busy = false; }
  }
  async function boot() {
    try { const result = await api<{username:string;csrf_token:string;ssh_enabled:boolean;poll_seconds:number}>('/session'); setCsrf(result.csrf_token); sshEnabled = result.ssh_enabled; pollSeconds = result.poll_seconds; authenticated = true; await loadDevices(); if (page === 'settings') await loadAudits(); }
    catch (error) { authenticated = false; if (!(error instanceof ApiError && error.status === 401)) loginError = error instanceof Error ? error.message : '后端连接失败'; }
    finally { starting = false; }
  }
  async function logout() { try { await api('/logout','POST'); authenticated = false; devices = []; setCsrf(''); } catch (error) { handleError(error); } }
  async function refresh() {
    if (!selected || busy) return; busy = true;
    try { await api(`/devices/${selected.id}/refresh`, 'POST'); await loadDevices(); notify('设备数据已刷新'); } catch (error) { handleError(error); } finally { busy = false; }
  }
  function openForm(device?: Device) {
    editId = device?.id || ''; form = device ? JSON.parse(JSON.stringify(device)) : emptyForm();
    gitPaths = form.git_paths.join('\n'); healthTargets = form.health_targets.map(item => `${item.name} | ${item.url}`).join('\n'); formError = ''; deviceDialog.showModal();
  }
  async function saveDevice(event: SubmitEvent) {
    event.preventDefault(); busy = true; formError = '';
    try {
      const targets = healthTargets.split('\n').filter(line => line.trim()).map(line => { const split = line.indexOf('|'); if (split < 1) throw new Error('健康检查每行格式：名称 | http://地址'); return {name:line.slice(0,split).trim(),url:line.slice(split+1).trim()}; });
      const payload = {...form,port:Number(form.port),jump_device_id:form.jump_device_id || null,git_paths:gitPaths.split('\n').map(line => line.trim()).filter(Boolean),health_targets:targets};
      const result = await api<Device>(`/devices${editId ? '/' + editId : ''}`, editId ? 'PUT' : 'POST', payload);
      selectedId = result.id; await loadDevices(); deviceDialog.close(); notify(editId ? '设备配置已更新' : '设备已添加');
    } catch (error) { formError = error instanceof Error ? error.message : '保存失败'; } finally { busy = false; }
  }
  function askConfirm(title: string, text: string, action: () => Promise<void>) { confirmTitle = title; confirmText = text; confirmAction = action; confirmDialog.showModal(); }
  function deleteDevice(device: Device) { askConfirm(`移除 ${device.name}？`, '这会删除控制台中的设备配置与历史采样。远程设备上的文件和服务不会被修改。', async () => { await api(`/devices/${device.id}`, 'DELETE'); await loadDevices(); notify('设备已移除'); }); }
  async function performConfirm() { busy = true; try { await confirmAction(); confirmDialog.close(); } catch (error) { handleError(error); } finally { busy = false; } }
  async function downloadBackup() {
    try { const data = await api('/config/backup'); const url = URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'})); const link = document.createElement('a'); link.href = url; link.download = 'homelab-config.json'; link.click(); URL.revokeObjectURL(url); notify('配置已导出，文件不含 SSH 密钥或登录凭据'); } catch (error) { handleError(error); }
  }
  async function restoreBackup(event: Event) {
    const input = event.target as HTMLInputElement; const file = input.files?.[0]; if (!file) return;
    try { if (file.size > 131072) throw new Error('配置文件不能超过 128 KiB'); const data = JSON.parse(await file.text()); askConfirm('恢复设备配置？','将替换现有设备配置并清空历史采样。SSH 凭据仍由服务端独立管理。', async () => { await api('/config/restore','POST',data); await loadDevices(); await loadAudits(); notify('配置已恢复，等待下一次采集'); }); } catch (error) { handleError(error); } finally { input.value = ''; }
  }
  async function loadLogs() {
    if (!selected) return; const id = ++logRequest; logLoading = true; logError = '';
    try { const result = await api<{lines:string[]}>(`/devices/${selected.id}/logs?source=${logSource}&target=${encodeURIComponent(logTarget)}&limit=500`); if (id === logRequest) logLines = result.lines; }
    catch (error) { if (id === logRequest) { logLines = []; logError = error instanceof Error ? error.message : '读取日志失败'; } } finally { if (id === logRequest) logLoading = false; }
  }
  function viewLogs(source: string, target: string) { logSource = source; logTarget = target; navigate('logs'); void loadLogs(); }
  function changeLogSource() { logTarget = ''; logLines = []; logError = ''; logRequest++; logLoading = false; }

  onMount(() => {
    dark = localStorage.getItem('hcc-theme') !== 'light'; document.documentElement.dataset.theme = dark ? 'dark' : 'light';
    const hash = location.hash.slice(1); if (navigation.some(item => item.id === hash)) page = hash as Page;
    void boot();
    const interval = setInterval(() => { if (authenticated && !document.hidden && !busy) void loadDevices(); }, 10000);
    const keyboard = (event: KeyboardEvent) => { if ((event.metaKey || event.ctrlKey) && event.key === 'k') { event.preventDefault(); searchInput?.focus(); } };
    window.addEventListener('keydown',keyboard);
    return () => { clearInterval(interval); clearTimeout(timer); window.removeEventListener('keydown',keyboard); };
  });
</script>

<svelte:head><title>Homelab — 你的个人基础设施控制台</title><meta name="description" content="通过安全 SSH 只读监控你的设备、容器、服务和代码项目。" /></svelte:head>

{#if starting}
  <div class="startup"><span class="brand-mark"><Icon name="server" size={25}/></span><p>正在连接你的控制台…</p></div>
{:else if !authenticated}
  <main class="login-shell">
    <section class="login-story">
      <div class="brand"><span class="brand-mark"><Icon name="server" size={24}/></span>homelab<span class="brand-dot">.</span></div>
      <div class="login-story-copy"><span class="eyebrow">YOUR INFRASTRUCTURE, IN FOCUS</span><h1>为你的数字世界，<br/>留一个指挥席。</h1><p>设备、容器、服务和代码。<br/>一个安静、清晰、属于你的控制中心。</p>
        <div class="network-art" aria-hidden="true"><div class="network-center"><Icon name="server" size={35}/><span>homelab</span></div><div class="network-node n1"><Icon name="box"/><span>containers</span></div><div class="network-node n2"><Icon name="activity"/><span>services</span></div><div class="network-node n3"><Icon name="git"/><span>projects</span></div><div class="orbit o1"></div><div class="orbit o2"></div></div>
      </div><div class="login-foot"><span class="status-dot"></span> 本地优先 · 安全连接 · 只读监控</div>
    </section>
    <section class="login-panel"><form onsubmit={login}><span class="eyebrow">WELCOME HOME</span><h2>登录控制台</h2><p class="muted">用管理员账户，连接你的 Homelab。</p><label>用户名<input name="username" autocomplete="username" bind:value={username} required /></label><label>密码<input name="password" type="password" autocomplete="current-password" bind:value={password} required /></label>{#if loginError}<div class="form-error" role="alert">{loginError}</div>{/if}<button class="primary login-button" type="submit" disabled={busy}>{busy ? '正在验证…' : '登录'}<Icon name="arrow" size={18}/></button><div class="login-note"><Icon name="lock" size={16}/><span>首次使用请在部署终端获取初始管理员密码。</span></div></form></section>
  </main>
{:else}
  <div class="app-shell">
    <aside class:mobile-open={mobileNav}>
      <button class="brand" onclick={() => navigate('overview')}><span class="brand-mark"><Icon name="server" size={23}/></span>homelab<span class="brand-dot">.</span></button>
      <div class="workspace"><span class="workspace-icon">H</span><span><strong>Personal workspace</strong><small>我的家庭实验室</small></span><span class="workspace-dots">⌘</span></div>
      <div class="nav-heading">工作空间</div>
      <nav aria-label="主导航">{#each navigation as item}<button class:active={page === item.id} onclick={() => navigate(item.id)} aria-current={page === item.id ? 'page' : undefined}><Icon name={item.icon} size={19}/><span>{item.label}</span>{#if item.id === 'devices'}<span class="nav-count">{devices.length}</span>{/if}{#if item.id === 'systemd' && issueCount}<span class="nav-count warning">{issueCount}</span>{/if}</button>{/each}</nav>
      <div class="sidebar-bottom"><div class="readonly-card"><Icon name="shield" size={19}/><div><strong>只读监控已启用</strong><p>安心查看你的基础设施</p></div></div><button class="profile" onclick={logout} title="退出登录"><span class="avatar">A</span><span><strong>{username}</strong><small>管理员</small></span><Icon name="logout" size={17}/></button><div class="sidebar-version"><span class="status-dot"></span> Control Center <span>v0.1.0</span></div></div>
    </aside>

    <div class="main-shell">
      <header class="topbar"><div class="breadcrumbs"><button class="mobile-toggle icon-button" aria-label="切换导航" onclick={() => mobileNav = !mobileNav}><Icon name="grid"/></button><span>工作空间</span><Icon name="chevron" size={13}/><strong>{navigation.find(item => item.id === page)?.label}</strong></div><div class="topbar-right"><div class="search-box"><Icon name="search" size={16}/><input bind:this={searchInput} aria-label="筛选当前页面" placeholder="搜索当前页面…" bind:value={search}/><kbd>⌘ K</kbd></div><button class="icon-button" onclick={setTheme} aria-label={dark ? '切换浅色模式' : '切换深色模式'}><Icon name={dark ? 'sun' : 'moon'} size={19}/></button><span class="top-avatar">A</span></div></header>
      <main class="content">
        <div class="page-heading"><div><div class="eyebrow">{page === 'overview' ? 'HOME INFRASTRUCTURE' : navigation.find(item => item.id === page)?.id.toUpperCase()} <span class="eyebrow-line"></span> CONTROL CENTER</div><h1>{titles[page]}</h1><p class="page-description">{page === 'overview' ? '所有设备的运行状态，汇集于此。' : '通过经过验证的 SSH 连接，安全地读取设备状态。'}</p></div><div class="heading-actions"><button class="button" onclick={refresh} disabled={!selected || busy}><Icon name="refresh" size={16}/>{busy ? '采集中…' : '刷新'}</button><button class="primary" onclick={() => openForm()}><Icon name="plus" size={17}/>添加设备</button></div></div>

        {#if devices.some(item => item.mode === 'demo')}<div class="demo-banner"><span class="demo-tag">DEMO</span><span>当前包含模拟设备数据。添加 SSH 设备后即可查看真实指标。</span><span class="banner-end"><Icon name="shield" size={14}/>只读模式</span></div>{/if}

        {#if page === 'overview'}
          <section class="summary-grid" aria-label="设备统计">
            <div class="summary-card"><div class="summary-label">在线设备<Icon name="server" size={18}/></div><div class="summary-value">{online.length}<span>/ {devices.length}</span></div><div class="summary-foot"><span class="status-dot"></span>{devices.length - online.length} 台离线或待连接<span class="mini-caption">DEVICES</span></div></div>
            <div class="summary-card"><div class="summary-label">平均 CPU 使用率<Icon name="cpu" size={18}/></div><div class="summary-value">{online.length ? (online.reduce((sum,item)=>sum+(item.snapshot?.metrics?.cpu_percent || 0),0)/online.length).toFixed(1) : '—'}<span>%</span></div><div class="summary-foot"><span class="muted">在线设备平均值</span><span class="mini-caption">COMPUTE</span></div></div>
            <div class="summary-card"><div class="summary-label">运行中容器<Icon name="box" size={18}/></div><div class="summary-value">{runningCount}<span>个</span></div><div class="summary-foot"><span class="status-dot"></span>Docker 工作负载<span class="mini-caption">CONTAINERS</span></div></div>
            <div class="summary-card"><div class="summary-label">需要关注<Icon name="alert" size={18}/></div><div class="summary-value amber">{issueCount}<span>项</span></div><div class="summary-foot"><span class="amber">设备或系统服务异常</span><button class="text-button" onclick={()=>navigate('systemd')}>查看<Icon name="arrow" size={13}/></button></div></div>
          </section>

          <div class="section-heading"><h2>我的设备<span class="count">{devices.length.toString().padStart(2,'0')}</span></h2><button class="text-button" onclick={()=>navigate('devices')}>管理设备<Icon name="arrow" size={15}/></button></div>
          <section class="device-grid" aria-label="设备概览">{#each devices.filter(item=>matches(item.name,item.host)) as device}<button class="device-card" class:selected={selected?.id === device.id} onclick={()=>selectDevice(device.id)}><div class="device-card-top"><span class="device-icon"><Icon name={device.kind === 'nas' ? 'disk' : 'server'} size={23}/></span><span class="status-pill" class:online={device.snapshot?.status==='online'}><span class="status-dot"></span>{statusName(device.snapshot?.status)}</span></div><div class="device-title"><h3>{device.name}</h3>{#if device.mode==='demo'}<span class="tiny-tag">模拟</span>{/if}</div><p class="device-subtitle">{device.snapshot?.os || (device.kind === 'windows' ? 'Windows · 待接入' : 'Linux · 待连接')}</p><div class="device-mini-metrics"><div><span>CPU</span><strong>{device.snapshot?.metrics?.cpu_percent ?? '—'}<small>%</small></strong><div class="mini-bar"><i style={`width:${device.snapshot?.metrics?.cpu_percent || 0}%`}></i></div></div><div><span>内存</span><strong>{device.snapshot?.metrics?.memory_percent ?? '—'}<small>%</small></strong><div class="mini-bar blue"><i style={`width:${device.snapshot?.metrics?.memory_percent || 0}%`}></i></div></div></div><div class="device-card-bottom"><span><Icon name="network" size={13}/>{device.host}</span><Icon name="chevron" size={15}/></div></button>{:else}<div class="empty-state">没有匹配的设备。<button class="text-button" onclick={()=>openForm()}>添加第一台设备</button></div>{/each}</section>
        {/if}

        {#if page !== 'overview' && page !== 'settings'}
          <div class="device-filter"><span>当前设备</span><select aria-label="选择设备" value={selected?.id || ''} onchange={event=>selectDevice(event.currentTarget.value)}>{#each devices as device}<option value={device.id}>{device.name}{device.mode==='demo' ? ' · 模拟' : ''}</option>{/each}</select>{#if selected}<span class="mono muted">{selected.host}:{selected.port}</span>{/if}</div>
        {/if}

        {#if selected && snapshot?.error && page !== 'settings'}<div class="error-banner"><Icon name="alert" size={18}/><div><strong>{snapshot.error.code === 'planned_device' ? '设备离线' : '设备连接提示'}</strong><p>{snapshot.error.message}</p>{#if metrics}<small>下方为上一次成功采集的数据，请勿作为当前状态。</small>{/if}</div></div>{/if}

        {#if page === 'overview' || page === 'devices'}
          {#if selected}
            <div class="overview-columns">
              <section class="panel resource-panel"><div class="panel-heading"><div><h2>资源趋势<span class="panel-context">{selected.name}</span></h2><p>最近 {history.length} 次采样 · 每 {pollSeconds} 秒更新</p></div><span class="live-label" class:inactive={snapshot?.status!=='online'}><span class="status-dot"></span>{snapshot?.status==='online' ? '正在采集' : '未连接'}</span></div><div class="chart-tabs">{#each [{id:'cpu_percent' as const,label:'CPU',value:metrics?.cpu_percent,color:'var(--accent)'},{id:'memory_percent' as const,label:'内存',value:metrics?.memory_percent,color:'var(--blue)'},{id:'disk_percent' as const,label:'磁盘',value:metrics?.disk_percent,color:'var(--amber)'}] as metric}<button class:active={metricTab===metric.id} onclick={()=>metricTab=metric.id}><span class="metric-dot" style={`background:${metric.color}`}></span>{metric.label}<strong>{metric.value ?? '—'}<small>%</small></strong></button>{/each}</div><div class="chart-area"><div class="chart-y"><span>100%</span><span>75%</span><span>50%</span><span>25%</span><span>0%</span></div><div class="chart-plot"><div class="chart-grid"><i></i><i></i><i></i><i></i><i></i></div><Sparkline values={history.map(sample=>sample[metricTab])} height={180} filled color={metricTab==='cpu_percent' ? 'var(--accent)' : metricTab==='memory_percent' ? 'var(--blue)' : 'var(--amber)'}/>{#if history.length<2}<span class="chart-wait">等待下一次采样，即可显示趋势</span>{/if}<div class="chart-x"><span>{history.length ? date(history[0].timestamp) : '—'}</span><span>现在</span></div></div></div><div class="resource-footer"><span><Icon name="clock" size={14}/>运行 {metrics ? uptime(metrics.uptime) : '—'}</span><span>最近采样 {date(snapshot?.timestamp)}</span></div></section>
              <section class="panel health-preview"><div class="panel-heading"><div><h2>服务健康</h2><p>从所选设备探测服务</p></div><Icon name="heart" size={19}/></div><div class="health-list">{#each checks as check}<div class="health-row"><span class="health-icon" class:bad={check.status!=='healthy'}><Icon name={check.status==='healthy' ? 'check' : 'alert'} size={16}/></span><div><strong>{check.name}</strong><small class="mono">{check.code || '无响应'} · {check.latency_ms != null ? check.latency_ms+' ms' : '—'}</small></div><span class="health-state" class:amber={check.status!=='healthy'}>{check.status==='healthy' ? '正常' : '异常'}</span></div>{:else}<div class="empty-state small">暂无健康检查<br/><span>编辑设备以添加检查地址</span></div>{/each}</div><button class="panel-footer-button" onclick={()=>navigate('health')}>查看所有健康检查<Icon name="arrow" size={15}/></button></section>
            </div>
            {#if page === 'devices'}
              <section class="panel"><div class="panel-heading"><div><h2>{selected.name}<span class="tiny-tag">{selected.mode==='demo'?'模拟设备':'SSH'}</span></h2><p>{snapshot?.os || '等待采集'} · {snapshot?.kernel || '内核信息待采集'}</p></div><div class="inline-actions"><button class="button" onclick={()=>openForm(selected)}><Icon name="edit" size={15}/>编辑配置</button><button class="button danger" onclick={()=>deleteDevice(selected)}>移除设备</button></div></div><div class="detail-grid"><div><span>主机名</span><strong>{snapshot?.hostname || '—'}</strong></div><div><span>SSH 地址</span><strong class="mono">{selected.host}:{selected.port}</strong></div><div><span>认证配置</span><strong>{selected.credential_ref}</strong></div><div><span>系统负载 · 1 / 5 / 15 分钟</span><strong>{metrics?.load.map(value=>value.toFixed(2)).join(' / ') || '—'}</strong></div><div><span>网络接收</span><strong>{metrics ? bytes(metrics.network_rx)+'/s' : '—'}</strong></div><div><span>网络发送</span><strong>{metrics ? bytes(metrics.network_tx)+'/s' : '—'}</strong></div></div><div class="disk-list">{#each metrics?.disks || [] as disk}<div><div class="disk-label"><span><Icon name="disk" size={15}/><span class="mono">{disk.mount}</span></span><span>{bytes(disk.used)} / {bytes(disk.total)}<strong>{disk.percent}%</strong></span></div><div class="mini-bar"><i style={`width:${disk.percent}%`}></i></div></div>{/each}</div></section>
            {:else}
              <section class="panel"><div class="panel-heading"><div><h2>容器动态<span class="panel-context">{selected.name}</span></h2></div><button class="text-button" onclick={()=>navigate('docker')}>查看 Docker<Icon name="arrow" size={15}/></button></div><div class="table-wrap"><table><thead><tr><th>容器名称</th><th>状态</th><th>CPU</th><th>内存</th><th class="right">日志</th></tr></thead><tbody>{#each containers.filter(item=>matches(item.name,item.image)).slice(0,4) as item}<tr><td><div class="table-name"><span class="container-icon"><Icon name="box" size={17}/></span><div><strong>{item.name}</strong><small>{item.image}</small></div></div></td><td><span class="status-pill" class:online={item.state==='running'}><span class="status-dot"></span>{item.state}</span></td><td class="mono">{item.cpu}</td><td class="mono">{item.memory.split(' / ')[0]}</td><td class="right"><button class="icon-button" aria-label={`查看 ${item.name} 日志`} onclick={()=>viewLogs('container',item.name)}><Icon name="terminal" size={17}/></button></td></tr>{:else}<tr><td colspan="5" class="table-empty">{snapshot?.docker?.error || '暂无容器数据'}</td></tr>{/each}</tbody></table></div></section>
            {/if}
          {:else}<div class="empty-state">还没有设备。添加设备，开始监控你的 Homelab。</div>{/if}
        {/if}

        {#if page === 'docker'}
          <section class="panel"><div class="panel-heading"><div><h2>Docker 工作负载</h2><p>{containers.filter(item=>item.state==='running').length} 个运行中 · {containers.length} 个容器</p></div><Icon name="box"/></div>{#if snapshot?.docker?.error}<div class="inline-error">{snapshot.docker.error}</div>{/if}<div class="tabs">{#each [{id:'containers' as const,label:'容器',count:containers.length},{id:'images' as const,label:'镜像',count:snapshot?.docker?.images.length || 0},{id:'compose' as const,label:'Compose 项目',count:snapshot?.docker?.compose.length || 0}] as tab}<button class:active={dockerTab===tab.id} onclick={()=>dockerTab=tab.id}>{tab.label}<span>{tab.count}</span></button>{/each}</div><div class="table-wrap"><table>{#if dockerTab==='containers'}<thead><tr><th>容器</th><th>状态</th><th>CPU / 内存</th><th>端口</th><th>日志</th></tr></thead><tbody>{#each containers.filter(item=>matches(item.name,item.image)) as item}<tr><td><strong>{item.name}</strong><small class="table-small mono">{item.image}</small></td><td><span class="status-pill" class:online={item.state==='running'}>{item.state}</span><small class="table-small">{item.status}</small></td><td class="mono">{item.cpu}<small class="table-small">{item.memory}</small></td><td class="mono">{item.ports || '—'}</td><td><button class="button" onclick={()=>viewLogs('container',item.name)}><Icon name="terminal" size={15}/>日志</button></td></tr>{:else}<tr><td colspan="5" class="table-empty">暂无匹配的容器</td></tr>{/each}</tbody>{:else if dockerTab==='images'}<thead><tr><th>镜像仓库</th><th>标签</th><th>镜像 ID</th><th>大小</th></tr></thead><tbody>{#each (snapshot?.docker?.images || []).filter(item=>matches(item.Repository,item.Tag)) as image}<tr><td class="mono">{image.Repository}</td><td><span class="tiny-tag">{image.Tag}</span></td><td class="mono muted">{image.ID}</td><td>{image.Size}</td></tr>{:else}<tr><td colspan="4" class="table-empty">暂无镜像数据</td></tr>{/each}</tbody>{:else}<thead><tr><th>项目名称</th><th>状态</th><th>配置文件</th></tr></thead><tbody>{#each (snapshot?.docker?.compose || []).filter(item=>matches(item.Name)) as project}<tr><td><strong>{project.Name}</strong></td><td>{project.Status}</td><td class="mono">{project.ConfigFiles}</td></tr>{:else}<tr><td colspan="3" class="table-empty">暂无 Compose 项目，或 Docker Compose 插件不可用</td></tr>{/each}</tbody>{/if}</table></div></section>
        {/if}

        {#if page === 'systemd'}
          <section class="panel"><div class="panel-heading"><div><h2>systemd 服务</h2><p>{services.length} 个服务 · {services.filter(item=>item.active==='failed').length} 个失败</p></div><span class="tiny-tag">只读</span></div>{#if snapshot?.systemd?.error}<div class="inline-error">{snapshot.systemd.error}</div>{/if}<div class="table-wrap"><table><thead><tr><th>服务</th><th>状态</th><th>子状态</th><th>运行历史与日志</th></tr></thead><tbody>{#each services.filter(item=>matches(item.name,item.description)).toSorted((a,b)=>Number(b.active==='failed')-Number(a.active==='failed')) as service}<tr><td><strong class="mono">{service.name}</strong><small class="table-small">{service.description}</small></td><td><span class="status-pill" class:online={service.active==='active'} class:failed={service.active==='failed'}><span class="status-dot"></span>{service.active}</span></td><td class="mono muted">{service.sub}</td><td><button class="button" onclick={()=>viewLogs('service',service.name)}><Icon name="terminal" size={15}/>Journal 日志</button></td></tr>{:else}<tr><td colspan="4" class="table-empty">暂无匹配的 systemd 服务</td></tr>{/each}</tbody></table></div></section>
        {/if}

        {#if page === 'git'}
          <div class="repo-grid">{#each repos.filter(repo=>matches(repo.name,repo.path,repo.branch)) as repo}<section class="panel repo-card"><div class="repo-heading"><span class="repo-icon"><Icon name="git" size={22}/></span><span class="status-pill" class:online={!repo.dirty&&!repo.error}>{repo.error ? '不可读取' : repo.dirty ? repo.changes+' 处变更' : '工作区干净'}</span></div><h2>{repo.name || repo.path}</h2><p class="mono muted repo-path">{repo.path}</p>{#if repo.error}<div class="inline-error">{repo.error}</div>{:else}<div class="branch"><Icon name="git" size={15}/>{repo.branch}</div><div class="commit"><span class="mono">{repo.commit}</span><p>{repo.message}</p><small>{repo.relative_time}</small></div>{/if}</section>{:else}<div class="panel empty-state"><Icon name="git" size={28}/><h3>还没有配置 Git 仓库</h3><p>编辑当前设备，添加需要读取的仓库绝对路径。</p><button class="button" onclick={()=>selected && openForm(selected)}>配置仓库路径</button></div>{/each}</div>
        {/if}

        {#if page === 'logs'}
          <section class="panel log-panel"><div class="panel-heading"><div><h2>日志浏览器</h2><p>按需读取最近 500 行 · 已知格式的凭据自动脱敏</p></div><span class="tiny-tag">{selected?.mode==='demo'?'模拟日志':'SSH 只读'}</span></div><div class="log-controls"><select aria-label="日志来源" bind:value={logSource} onchange={changeLogSource}><option value="system">系统 Journal</option><option value="container">Docker 容器</option><option value="service">systemd 服务</option></select>{#if logSource!=='system'}<select aria-label="日志目标" bind:value={logTarget}><option value="">选择{logSource==='container'?'容器':'服务'}</option>{#each logSource==='container'?containers:services as item}<option value={item.name}>{item.name}</option>{/each}</select>{/if}<button class="primary" onclick={loadLogs} disabled={logLoading||!selected||(logSource!=='system'&&!logTarget)}><Icon name="refresh" size={15}/>{logLoading?'读取中…':'读取日志'}</button><div class="log-filter"><Icon name="search" size={15}/><input aria-label="搜索日志内容" placeholder="搜索日志内容…" bind:value={logSearch}/></div><select aria-label="日志级别" bind:value={logLevel}><option value="all">所有级别</option><option value="error">ERROR</option><option value="warn">WARN</option><option value="info">INFO</option><option value="debug">DEBUG</option></select></div>{#if logError}<div class="inline-error" role="alert">{logError}</div>{/if}<div class="terminal" aria-live="polite">{#each visibleLines as line,i}<div class:error-line={/error|fail/i.test(line)} class:warn-line={/warn/i.test(line)&&!/error|fail/i.test(line)}><span class="line-number">{i+1}</span><code>{line}</code></div>{:else}<div class="terminal-empty"><Icon name="terminal" size={30}/><p>{logLoading ? '正在读取日志…' : logLines.length ? '没有匹配的日志' : '选择日志来源，点击「读取日志」开始查看。'}</p></div>{/each}</div><div class="resource-footer"><span>{visibleLines.length} 行显示 / {logLines.length} 行已读取</span><span>不持续追踪 · 不提供命令输入</span></div></section>
        {/if}

        {#if page === 'health'}
          <div class="health-grid">{#each checks.filter(check=>matches(check.name,check.url)) as check}<section class="panel health-check-card"><div class="repo-heading"><span class="health-icon" class:bad={check.status!=='healthy'}><Icon name={check.status==='healthy'?'check':'alert'} size={21}/></span><span class="status-pill" class:online={check.status==='healthy'}>{check.status==='healthy'?'服务正常':'服务异常'}</span></div><h2>{check.name}</h2><p class="mono muted">{check.url}</p><div class="health-check-stats"><div><span>HTTP 状态</span><strong>{check.code || '—'}</strong></div><div><span>响应时间</span><strong>{check.latency_ms ?? '—'}<small>ms</small></strong></div></div>{#if check.error}<p class="amber">{check.error}</p>{/if}</section>{:else}<div class="panel empty-state"><Icon name="heart" size={28}/><h3>添加第一个健康检查</h3><p>检查从远程设备发起，支持家庭内网服务。</p><button class="button" onclick={()=>selected && openForm(selected)}>配置健康检查</button></div>{/each}</div>
        {/if}

        {#if page === 'settings'}
          <div class="settings-grid"><section class="panel"><div class="panel-heading"><div><h2>连接与安全</h2><p>第一阶段 · 只读监控</p></div><Icon name="shield" size={20}/></div><div class="settings-rows"><div><span>SSH 主入口</span><strong class="mono">hemu-server.top</strong></div><div><span>真实 SSH</span><span class="status-pill" class:online={sshEnabled}>{sshEnabled?'已启用':'等待凭据配置'}</span></div><div><span>主机密钥校验</span><strong>严格校验 · 不自动信任</strong></div><div><span>远程管理操作</span><strong>第一阶段不提供</strong></div><div><span>采样周期 / 历史保留</span><strong>{pollSeconds} 秒 / 7 天</strong></div><div><span>管理员会话</span><strong>8 小时 · HttpOnly Cookie</strong></div></div></section><section class="panel"><div class="panel-heading"><div><h2>配置备份与恢复</h2><p>保留设备、仓库和健康检查配置</p></div><Icon name="download" size={19}/></div><div class="backup-content"><p>配置文件不含 SSH 密钥、认证密码或登录会话。迁移时，凭据需要在目标服务器单独配置。</p><div class="inline-actions"><button class="primary" onclick={downloadBackup}><Icon name="download" size={16}/>导出配置</button><button class="button" onclick={()=>restoreInput?.click()}>从文件恢复</button><input class="visually-hidden" bind:this={restoreInput} type="file" accept="application/json,.json" onchange={restoreBackup}/></div></div></section></div>
          <section class="panel"><div class="panel-heading"><div><h2>审计记录</h2><p>最近 100 条管理与访问记录</p></div><button class="button" onclick={loadAudits}><Icon name="refresh" size={15}/>刷新</button></div><div class="table-wrap"><table><thead><tr><th>时间</th><th>操作</th><th>目标</th><th>详情</th></tr></thead><tbody>{#each audits.filter(item=>matches(item.action,item.target,item.detail)) as item}<tr><td class="mono muted">{new Date(item.timestamp*1000).toLocaleString('zh-CN')}</td><td class="mono">{item.action}</td><td class="mono muted">{item.target || '—'}</td><td>{item.detail || '—'}</td></tr>{:else}<tr><td colspan="4" class="table-empty">暂无审计记录</td></tr>{/each}</tbody></table></div></section>
        {/if}

        <footer class="page-footer"><span><span class="status-dot"></span> 数据由服务端安全采集</span><span>Built for your corner of the internet.</span></footer>
      </main>
    </div>
  </div>
{/if}

<dialog bind:this={deviceDialog} class="device-dialog"><form onsubmit={saveDevice}><div class="dialog-heading"><div><span class="eyebrow">DEVICE CONFIGURATION</span><h2>{editId ? '编辑设备' : '接入一台设备'}</h2></div><button class="icon-button" type="button" aria-label="关闭设备配置" onclick={()=>deviceDialog.close()}><Icon name="close"/></button></div><div class="form-grid"><label>设备名称<input bind:value={form.name} required maxlength="64" placeholder="例如 ThinkBook"/></label><label>设备类型<select bind:value={form.kind}><option value="linux">Linux</option><option value="nas">NAS / Linux</option><option value="windows">Windows（仅演示）</option></select></label><label>数据来源<select bind:value={form.mode}><option value="ssh">真实 SSH</option><option value="demo">模拟设备</option></select></label><label>SSH 主机<input bind:value={form.host} required placeholder="hemu-server.top"/></label><label>SSH 端口<input type="number" min="1" max="65535" bind:value={form.port} required/></label><label>SSH 用户名<input bind:value={form.username} placeholder="使用服务端认证配置中的用户名"/></label><label>服务端认证配置名<input bind:value={form.credential_ref} required placeholder="thinkbook"/></label><label>SSH 跳板<select bind:value={form.jump_device_id}><option value={null}>直接连接</option>{#each devices.filter(item=>item.id!==editId&&item.mode==='ssh'&&!item.jump_device_id) as item}<option value={item.id}>{item.name}</option>{/each}</select></label><label class="full-width">Git 仓库路径 <span>每行一个绝对路径</span><textarea bind:value={gitPaths} rows="2" placeholder="/srv/projects/homelab"></textarea></label><label class="full-width">健康检查 <span>每行：名称 | URL，从该设备发起</span><textarea bind:value={healthTargets} rows="2" placeholder="Agent API | http://127.0.0.1:8081/health"></textarea></label></div><div class="form-note"><Icon name="lock" size={16}/><span>SSH 密钥仅在服务端配置，浏览器无法读取。连接需要已核验的主机密钥。</span></div>{#if formError}<div class="form-error" role="alert">{formError}</div>{/if}<div class="dialog-actions"><button type="button" class="button" onclick={()=>deviceDialog.close()}>取消</button><button type="submit" class="primary" disabled={busy}>{busy?'正在保存…':editId?'保存配置':'添加设备'}</button></div></form></dialog>
<dialog bind:this={confirmDialog} class="confirm-dialog"><div class="dialog-heading"><h2>{confirmTitle}</h2><button class="icon-button" aria-label="关闭确认" onclick={()=>confirmDialog.close()}><Icon name="close"/></button></div><p>{confirmText}</p><div class="dialog-actions"><button class="button" onclick={()=>confirmDialog.close()}>取消</button><button class="primary" disabled={busy} onclick={performConfirm}>{busy?'处理中…':'确认'}</button></div></dialog>
{#if toast}<div class="toast" class:toast-error={toastError} role="status"><Icon name={toastError?'alert':'check'} size={18}/>{toast}<button class="icon-button" aria-label="关闭提示" onclick={()=>toast=''}><Icon name="close" size={15}/></button></div>{/if}
