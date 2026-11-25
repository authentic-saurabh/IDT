import { useEffect, useState } from 'react'
import { BrowserRouter, NavLink, Route, Routes } from 'react-router-dom'
import {
  Activity, Bell, Bot, Boxes, ChevronRight, CircleGauge,
  Clock3, FileText, History, LayoutDashboard, Network, Search, Settings,
  ShieldCheck, TriangleAlert, UserCircle, Zap,
} from 'lucide-react'
import './App.css'

const API = 'http://localhost:8000'

type Cluster = {
  name: string; status: string; kubernetesVersion: string; nodeCount: number;
  podCount: number; healthyPods: number; unhealthyPods: number; error?: string
}
type NodeInfo = {
  name: string; role: string; status: string; cpuCapacity: string;
  memoryCapacity: string; cpuUsage: number | null; memoryUsage: number | null;
  podCount: number; kubernetesVersion: string; internalIp: string
}
type Incident = {
  id: string; timestamp: string; severity: string; resource_type: string;
  resource_name: string; namespace: string; metric: string; score: number;
  description: string; status: string; confidence?: number
}

const navigation = [
  { to: '/', label: 'Overview', icon: LayoutDashboard },
  { to: '/monitoring', label: 'Cluster Monitoring', icon: Activity },
  { to: '/nodes', label: 'Nodes', icon: Network },
  { to: '/workloads', label: 'Workloads & Pods', icon: Boxes },
  { to: '/ai', label: 'AI Intelligence', icon: Bot },
  { to: '/incidents', label: 'Incidents', icon: TriangleAlert },
  { to: '/recovery', label: 'Recovery History', icon: History },
  { to: '/analytics', label: 'Analytics', icon: CircleGauge },
  { to: '/settings', label: 'Settings', icon: Settings },
]

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API}${path}`)
  if (!response.ok) throw new Error(`API request failed: ${response.status}`)
  return response.json()
}

function Sidebar() {
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark"><ShieldCheck size={21} /></div>
        <div><strong>HealOps AI</strong><span>Intelligent Infrastructure</span></div>
      </div>
      <nav className="nav">
        {navigation.map(({ to, label, icon: Icon }) => (
          <NavLink key={to} to={to} end={to === '/'} className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <Icon size={18} /><span>{label}</span>
          </NavLink>
        ))}
      </nav>
      <div className="sidebar-bottom">
        <div className="system-status"><span className="status-dot" /><div><strong>System status</strong><small>Live monitoring</small></div></div>
        <button className="sidebar-link"><FileText size={17} /> Documentation</button>
        <div className="profile"><div className="avatar">AK</div><div><strong>Admin User</strong><small>Platform Administrator</small></div></div>
      </div>
    </aside>
  )
}

function Header({ title }: { title: string }) {
  return (
    <header className="topbar">
      <div><span className="breadcrumb">Platform <ChevronRight size={13} /> {title}</span><h1>{title}</h1></div>
      <div className="header-actions">
        <button className="cluster-select"><span className="status-dot" />kind-cluster <ChevronRight size={14} /></button>
        <span className="live-pill"><span className="pulse" />Live</span>
        <button className="icon-button" aria-label="Notifications"><Bell size={19} /><span className="notification-dot" /></button>
        <button className="icon-button" aria-label="User menu"><UserCircle size={21} /></button>
      </div>
    </header>
  )
}

function Shell({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="app-shell">
      <Sidebar />
      <main className="main">
        <Header title={title} />
        <div className="content">{children}</div>
      </main>
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  const tone = /ready|resolved|success|running|healthy|connected|normal/i.test(status) ? 'success'
    : /warning|investigat|pending/i.test(status) ? 'warning'
    : /critical|failed|not ready|disconnected/i.test(status) ? 'danger' : 'neutral'
  return <span className={`badge ${tone}`}><span />{status}</span>
}

function KpiCard({ title, value, icon: Icon, detail, tone = 'blue' }: {
  title: string; value: string | number; icon: typeof Activity; detail: string; tone?: string
}) {
  return (
    <article className="kpi-card">
      <div className={`kpi-icon ${tone}`}><Icon size={20} /></div>
      <div className="kpi-main"><span>{title}</span><strong>{value}</strong><small>{detail}</small></div>
    </article>
  )
}

function MetricChart({ title, dataKey = 'cpu', color = '#2563eb' }: { title: string; dataKey?: string; color?: string }) {
  const [data, setData] = useState<any>(null)
  useEffect(() => {
    getJson<any>(`/api/metrics/range?metric=${dataKey}&range=30m&step=30s`)
      .then(setData)
      .catch(() => setData({ available: false }))
  }, [dataKey])
  const available = data?.available
  const chartValues = available ? data.values.slice(-24) : []
  const chartNumbers = chartValues.map((item: any) => Number(item.value) || 0)
  const chartMin = chartNumbers.length ? Math.min(...chartNumbers) : 0
  const chartMax = chartNumbers.length ? Math.max(...chartNumbers) : 1
  return (
    <article className="card chart-card">
      <div className="card-heading"><div><h2>{title}</h2><p>Prometheus time series · Last 30 minutes</p></div><StatusBadge status={available ? 'Live' : 'Unavailable'} /></div>
      {available ? (
        <div className="chart-wrap live-chart">
          <div className="live-chart-bars" style={{ '--chart-color': color } as React.CSSProperties}>
            {chartValues.map((item: any, index: number) => (
              <span key={index} style={{ height: `${chartMax === chartMin ? 35 : 10 + ((Number(item.value) - chartMin) / (chartMax - chartMin)) * 90}%` }} />
            ))}
          </div>
        </div>
      ) : (
        <div className="chart-wrap empty-chart"><Activity size={20}/><span>{data?.message || 'Waiting for Prometheus metric series'}</span></div>
      )}
    </article>
  )
}

function Overview() {
  const [cluster, setCluster] = useState<Cluster | null>(null)
  const [nodes, setNodes] = useState<NodeInfo[]>([])
  const [incidents, setIncidents] = useState<Incident[]>([])
  const [recoveries, setRecoveries] = useState<any[]>([])
  useEffect(() => {
    getJson<Cluster>('/api/cluster').then(setCluster).catch(() => setCluster(null))
    getJson<NodeInfo[]>('/api/nodes').then(setNodes).catch(() => setNodes([]))
    getJson<Incident[]>('/api/incidents').then(setIncidents).catch(() => setIncidents([]))
    getJson<any[]>('/api/recovery/history').then(setRecoveries).catch(() => setRecoveries([]))
  }, [])
  const connected = cluster?.status === 'connected'
  return (
    <Shell title="Overview">
      <section className="welcome">
        <div><h2>Welcome back to HealOps AI</h2><p>Your Kubernetes infrastructure is continuously monitored by intelligent automation.</p></div>
        <div className="connection-summary"><span><i className={connected ? 'ok' : 'warn'} />Cluster {connected ? 'connected' : 'unavailable'}</span><span><i className="ok" />Monitoring {connected ? 'active' : 'degraded'}</span></div>
      </section>
      <section className="kpi-grid">
        <KpiCard title="Total Nodes" value={cluster?.nodeCount ?? '—'} icon={Network} detail={connected ? 'From Kubernetes API' : 'Waiting for Kubernetes'} />
        <KpiCard title="Healthy Pods" value={cluster?.healthyPods ?? '—'} icon={Boxes} detail={`${cluster?.podCount ?? 0} pods discovered`} tone="cyan" />
        <KpiCard title="Active Anomalies" value={incidents.filter(i => i.status !== 'Resolved').length} icon={TriangleAlert} detail="No severe anomaly" tone="amber" />
        <KpiCard title="Successful Recoveries" value={recoveries.filter(r => r.status !== 'Failed').length} icon={ShieldCheck} detail="Calculated from history" tone="green" />
      </section>
      <section className="card cluster-health">
        <div className="card-heading"><div><h2>Cluster health</h2><p>{cluster?.name ?? 'No cluster connected'} · Live infrastructure state</p></div><button className="text-button">View topology <ChevronRight size={14} /></button></div>
        {nodes.length ? (
          <div className="node-grid">
            {nodes.map(node => (
              <article className="node-card" key={node.name}>
                <div className="node-card-head"><div className="node-icon"><Network size={18} /></div><StatusBadge status={node.status} /></div>
                <h3>{node.name}</h3><p>{node.role} · {node.internalIp}</p>
                <div className="resource-row"><span>CPU</span><strong>{node.cpuUsage == null ? 'N/A' : `${node.cpuUsage}%`}</strong></div>
                <div className="progress"><span style={{ width: `${node.cpuUsage ?? 0}%` }} /></div>
                <div className="resource-row"><span>Memory</span><strong>{node.memoryUsage == null ? 'N/A' : `${node.memoryUsage}%`}</strong></div>
                <div className="progress indigo"><span style={{ width: `${node.memoryUsage ?? 0}%` }} /></div>
                <div className="node-footer"><span>{node.podCount} pods</span><span>{node.kubernetesVersion}</span></div>
              </article>
            ))}
          </div>
        ) : (
          <div className="empty-state"><Network size={28} /><h3>Kubernetes cluster unavailable</h3><p>Configure kubeconfig and ensure the cluster is running. No demo node values are being shown.</p></div>
        )}
      </section>
      <section className="charts-grid">
        <MetricChart title="CPU utilization" dataKey="cpu" color="#2563eb" />
        <MetricChart title="Memory utilization" dataKey="memory" color="#6366f1" />
      </section>
      <section className="bottom-grid">
        <article className="card">
          <div className="card-heading"><div><h2>Recent incidents</h2><p>Latest anomaly and recovery activity</p></div><NavLink className="text-button" to="/incidents">View all</NavLink></div>
          {incidents.length ? <table><thead><tr><th>Incident</th><th>Severity</th><th>Resource</th><th>Status</th></tr></thead><tbody>{incidents.slice(0,5).map(i => <tr key={i.id}><td>{i.id}</td><td><StatusBadge status={i.severity}/></td><td>{i.resource_name}</td><td><StatusBadge status={i.status}/></td></tr>)}</tbody></table> : <div className="compact-empty"><ShieldCheck size={20}/><span>No incidents stored</span></div>}
        </article>
        <article className="card ai-insight">
          <div className="card-heading"><div><h2>AI insights</h2><p>Isolation Forest engine</p></div><Bot size={20} /></div>
          {connected ? <div className="insight"><span className="insight-icon"><Activity size={18}/></span><div><strong>Live analysis active</strong><p>Insights will appear after baseline metrics are collected and analysed.</p></div></div> : <div className="insight neutral"><span className="insight-icon"><Clock3 size={18}/></span><div><strong>Waiting for data</strong><p>Connect Kubernetes and Prometheus to begin evidence-based analysis.</p></div></div>}
        </article>
      </section>
    </Shell>
  )
}

function NodesPage() {
  const [nodes, setNodes] = useState<NodeInfo[]>([])
  const [error, setError] = useState('')
  const [selected, setSelected] = useState<any>(null)
  useEffect(() => { getJson<NodeInfo[]>('/api/nodes').then(setNodes).catch(e => setError(e.message)) }, [])
  async function openNode(node: NodeInfo) {
    const detail = await getJson<any>(`/api/nodes/${encodeURIComponent(node.name)}`).catch(() => null)
    setSelected(detail)
  }
  return <Shell title="Nodes"><section className="card"><div className="card-heading"><div><h2>Cluster nodes</h2><p>Real Kubernetes node inventory</p></div></div>{error ? <div className="empty-state"><TriangleAlert/><h3>Unable to load nodes</h3><p>{error}</p></div> : nodes.length ? <table><thead><tr><th>Node</th><th>Role</th><th>Status</th><th>CPU capacity</th><th>Memory capacity</th><th>Pods</th><th>IP</th></tr></thead><tbody>{nodes.map(n => <tr key={n.name} className="clickable-row" onClick={() => openNode(n)}><td><strong>{n.name}</strong></td><td>{n.role}</td><td><StatusBadge status={n.status}/></td><td>{n.cpuCapacity}</td><td>{n.memoryCapacity}</td><td>{n.podCount}</td><td>{n.internalIp}</td></tr>)}</tbody></table> : <div className="empty-state"><Network/><h3>No nodes discovered</h3><p>No Kubernetes node data is available.</p></div>}</section>{selected ? <div className="detail-modal" role="dialog" aria-modal="true"><article className="card"><div className="card-heading"><div><h2>{selected.name}</h2><p>Node conditions and running workloads</p></div><button className="text-button" onClick={() => setSelected(null)}>Close</button></div><div className="pod-detail"><div><strong>Conditions</strong><span>{selected.conditions.map((c: any) => `${c.type}:${c.status}`).join(', ')}</span></div><div><strong>Running pods</strong><span>{selected.pods.length}</span></div><div><strong>Events</strong><span>{selected.events.length}</span></div><div><strong>Allocatable CPU</strong><span>{selected.allocatable.cpu || 'Unknown'}</span></div></div></article></div> : null}</Shell>
}

function WorkloadsPage() {
  const [pods, setPods] = useState<any[]>([])
  const [workloads, setWorkloads] = useState<any>(null)
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<any>(null)
  useEffect(() => {
    getJson<any[]>('/api/pods').then(setPods).catch(() => setPods([]))
    getJson<any>('/api/workloads').then(setWorkloads).catch(() => setWorkloads(null))
  }, [])
  const filtered = pods.filter(p => `${p.name} ${p.namespace}`.toLowerCase().includes(search.toLowerCase()))
  async function openPod(pod: any) {
    const detail = await getJson<any>(`/api/pods/${encodeURIComponent(pod.namespace)}/${encodeURIComponent(pod.name)}`).catch(() => null)
    setSelected(detail)
  }
  const workloadRows = workloads ? [
    ...workloads.deployments,
    ...workloads.statefulSets,
    ...workloads.daemonSets,
  ] : []
  return <Shell title="Workloads & Pods"><section className="card"><div className="card-heading"><div><h2>Workloads</h2><p>Deployments, StatefulSets, and DaemonSets</p></div></div>{workloadRows.length ? <table><thead><tr><th>Workload</th><th>Kind</th><th>Namespace</th><th>Ready</th><th>Desired</th></tr></thead><tbody>{workloadRows.map(w => <tr key={`${w.namespace}/${w.kind}/${w.name}`}><td><strong>{w.name}</strong></td><td>{w.kind}</td><td>{w.namespace}</td><td>{w.replicas}</td><td>{w.desired}</td></tr>)}</tbody></table> : <div className="empty-state"><Boxes/><h3>No workloads discovered</h3><p>Workloads appear when Kubernetes is connected.</p></div>}</section><section className="card" style={{marginTop:'14px'}}><div className="card-heading"><div><h2>Pods</h2><p>Workloads from the connected cluster</p></div><label className="search-box"><Search size={16}/><input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search pods or namespaces"/></label></div>{filtered.length ? <table><thead><tr><th>Pod</th><th>Namespace</th><th>Node</th><th>Status</th><th>Restarts</th><th>Ready</th></tr></thead><tbody>{filtered.map(p => <tr key={`${p.namespace}/${p.name}`} onClick={() => openPod(p)} className="clickable-row"><td><strong>{p.name}</strong></td><td>{p.namespace}</td><td>{p.node}</td><td><StatusBadge status={p.status}/></td><td>{p.restartCount}</td><td>{p.readyContainers}/{p.totalContainers}</td></tr>)}</tbody></table> : <div className="empty-state"><Boxes/><h3>No pods discovered</h3><p>Pods will appear when Kubernetes is connected.</p></div>}</section>{selected ? <div className="detail-modal" role="dialog" aria-modal="true"><article className="card"><div className="card-heading"><div><h2>{selected.name}</h2><p>{selected.namespace} · Pod details</p></div><button className="text-button" onClick={() => setSelected(null)}>Close</button></div><div className="pod-detail"><div><strong>Node</strong><span>{selected.node || 'Pending'}</span></div><div><strong>Status</strong><StatusBadge status={selected.status}/></div><div><strong>Containers</strong><span>{selected.containers.map((c: any) => c.name).join(', ')}</span></div><div><strong>Events</strong><span>{selected.events.length}</span></div></div></article></div> : null}</Shell>
}

function MonitoringPage() {
  const [nodes, setNodes] = useState<NodeInfo[]>([])
  useEffect(() => { getJson<NodeInfo[]>('/api/nodes').then(setNodes).catch(() => setNodes([])) }, [])
  return <Shell title="Cluster Monitoring"><div className="topology card"><div className="card-heading"><div><h2>Cluster topology</h2><p>Live Kubernetes node relationships</p></div></div>{nodes.length ? <div className="topology-flow">{nodes.map((node, index) => <span className="topology-step" key={node.name}>{index > 0 ? <ChevronRight/> : null}<div className="topology-node">{node.role === 'Control Plane' ? <ShieldCheck/> : <Network/>}<strong>{node.name}</strong><small><StatusBadge status={node.status}/></small></div></span>)}</div> : <div className="empty-state"><Network/><h3>No topology available</h3><p>Node relationships appear when Kubernetes is connected.</p></div>}</div><section className="charts-grid"><MetricChart title="CPU utilization" dataKey="cpu" color="#2563eb"/><MetricChart title="Memory utilization" dataKey="memory" color="#6366f1"/></section></Shell>
}

function AIPage() {
  const [status, setStatus] = useState<any>(null)
  const [analysis, setAnalysis] = useState<any>(null)
  const [cpu, setCpu] = useState('40')
  const [memory, setMemory] = useState('60')
  const [restarts, setRestarts] = useState('0')
  useEffect(() => { getJson<any>('/api/ai/status').then(setStatus).catch(() => setStatus(null)) }, [])
  async function analyse() {
    const response = await fetch(`${API}/api/ai/analyse`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cpu: Number(cpu), memory: Number(memory), restarts: Number(restarts) }),
    })
    if (response.ok) setAnalysis(await response.json())
  }
  return <Shell title="AI Intelligence"><section className="kpi-grid"><KpiCard title="Engine status" value={status?.status === 'running' ? 'Running' : 'Stopped'} icon={Bot} detail={status?.trained ? 'Model trained' : 'Baseline not complete'}/><KpiCard title="Anomalies detected" value={status?.anomalyCount ?? 0} icon={TriangleAlert} detail="Stored incidents" tone="amber"/><KpiCard title="Samples analysed" value={status?.samples ?? 0} icon={Activity} detail={`Minimum ${status?.baselineNeeded ?? 30}`} tone="cyan"/><KpiCard title="Contamination" value={status?.contamination ?? 0.05} icon={CircleGauge} detail="Isolation Forest parameter" tone="green"/></section><section className="bottom-grid"><article className="card"><div className="card-heading"><div><h2>Model information</h2><p>{status?.modelName ?? 'HealOps Isolation Forest'}</p></div><StatusBadge status={status?.trained ? 'Trained' : 'Collecting baseline'}/></div><div className="model-copy"><h3>Isolation Forest</h3><p>Isolation Forest identifies observations that differ from the learned baseline across CPU, memory, and restart features. It does not assume that any one metric is inherently anomalous.</p><div className="formula">score = isolation-depth anomaly score</div></div></article><article className="card"><div className="card-heading"><div><h2>Analyse observation</h2><p>Manual evidence-based analysis</p></div></div><div className="analysis-form"><label>CPU <input type="number" value={cpu} onChange={e => setCpu(e.target.value)}/></label><label>Memory <input type="number" value={memory} onChange={e => setMemory(e.target.value)}/></label><label>Restarts <input type="number" value={restarts} onChange={e => setRestarts(e.target.value)}/></label><button className="primary-button" onClick={analyse}>Analyse now</button>{analysis ? <div className="analysis-result"><StatusBadge status={analysis.severity || 'Normal'}/><div><p>{analysis.message}</p>{analysis.confidence != null ? <small>Anomaly confidence: {analysis.confidence}%</small> : null}</div></div> : null}</div></article></section></Shell>
}

function IncidentsPage() {
  const [incidents, setIncidents] = useState<Incident[]>([])
  const [selected, setSelected] = useState<any>(null)
  useEffect(() => { getJson<Incident[]>('/api/incidents').then(setIncidents).catch(() => setIncidents([])) }, [])
  async function openIncident(incident: Incident) {
    const detail = await getJson<any>(`/api/incidents/${encodeURIComponent(incident.id)}`).catch(() => null)
    setSelected(detail)
  }
  return <Shell title="Incidents"><section className="card"><div className="card-heading"><div><h2>Incident management</h2><p>Detected anomalies and remediation lifecycle</p></div></div>{incidents.length ? <table><thead><tr><th>Incident ID</th><th>Timestamp</th><th>Severity</th><th>Resource</th><th>Metric</th><th>AI confidence</th><th>Status</th></tr></thead><tbody>{incidents.map(i => <tr key={i.id} className="clickable-row" onClick={() => openIncident(i)}><td><strong>{i.id}</strong></td><td>{new Date(i.timestamp).toLocaleString()}</td><td><StatusBadge status={i.severity}/></td><td>{i.resource_name}</td><td>{i.metric}</td><td>{i.confidence != null ? `${i.confidence}%` : `${(i.score * 100).toFixed(1)}%`}</td><td><StatusBadge status={i.status}/></td></tr>)}</tbody></table> : <div className="empty-state"><ShieldCheck/><h3>No incidents recorded</h3><p>Anomalies will appear here when the AI pipeline creates evidence-backed incidents.</p></div>}</section>{selected ? <div className="detail-modal" role="dialog" aria-modal="true"><article className="card"><div className="card-heading"><div><h2>{selected.id}</h2><p>{selected.resource_name} · Incident timeline</p></div><button className="text-button" onClick={() => setSelected(null)}>Close</button></div><div className="timeline">{selected.timeline.map((item: any, index: number) => <div key={index} className="timeline-row"><span className="timeline-dot"/><div><strong>{item.step}</strong><p>{item.status}</p></div></div>)}</div></article></div> : null}</Shell>
}

function RecoveryPage() {
  const [history, setHistory] = useState<any[]>([])
  useEffect(() => { getJson<any[]>('/api/recovery/history').then(setHistory).catch(() => setHistory([])) }, [])
  async function verify(id: string) {
    await fetch(`${API}/api/recovery/${encodeURIComponent(id)}/verify`, { method: 'POST' })
    getJson<any[]>('/api/recovery/history').then(setHistory).catch(() => setHistory([]))
  }
  return <Shell title="Recovery History"><section className="kpi-grid"><KpiCard title="Recovery attempts" value={history.length} icon={Zap} detail="All recorded operations"/><KpiCard title="Successful" value={history.filter(r => r.status === 'Resolved').length} icon={ShieldCheck} detail="Verified against live pod health" tone="green"/><KpiCard title="Failed" value={history.filter(r => r.status === 'Failed').length} icon={TriangleAlert} detail="No API success assumed" tone="amber"/><KpiCard title="Avg. recovery confidence" value={history.length ? `${Math.round(history.reduce((sum, r) => sum + (r.estimatedSuccess || 0), 0) / history.length)}%` : '—'} icon={CircleGauge} detail="Estimated from anomaly + history" tone="cyan"/></section><section className="card"><div className="card-heading"><div><h2>Recovery history</h2><p>Verified Kubernetes remediation actions</p></div></div>{history.length ? <table><thead><tr><th>Recovery ID</th><th>Workload</th><th>Action</th><th>Started</th><th>Duration</th><th>Anomaly confidence</th><th>Est. success</th><th>Verification</th><th>Status</th><th></th></tr></thead><tbody>{history.map(r => <tr key={r.id}><td><strong>{r.id}</strong></td><td>{r.workload}</td><td>{r.action}</td><td>{new Date(r.start_time).toLocaleString()}</td><td>{r.duration_seconds?.toFixed(1)}s</td><td>{r.confidence != null ? `${r.confidence}%` : '—'}</td><td>{r.estimatedSuccess != null ? `${r.estimatedSuccess}%` : '—'}</td><td>{r.verification}</td><td><StatusBadge status={r.status}/></td><td>{r.status === 'Verification Pending' || r.status === 'Verification Failed' ? <button className="text-button" onClick={() => verify(r.id)}>Verify</button> : null}</td></tr>)}</tbody></table> : <div className="empty-state"><History/><h3>No recovery attempts</h3><p>No recovery operation has been executed.</p></div>}</section></Shell>
}

function AnalyticsPage() {
  const [summary, setSummary] = useState<any>(null)
  const [greenops, setGreenops] = useState<any>(null)
  useEffect(() => {
    getJson<any>('/api/analytics/summary').then(setSummary).catch(() => setSummary(null))
    getJson<any>('/api/analytics/greenops').then(setGreenops).catch(() => setGreenops(null))
  }, [])
  async function exportCsv() {
    const incidents = await getJson<Incident[]>('/api/incidents').catch(() => [])
    const rows = ['Incident ID,Timestamp,Severity,Resource,Status', ...incidents.map(i => [i.id, i.timestamp, i.severity, i.resource_name, i.status].join(','))]
    const blob = new Blob([rows.join('\n')], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = 'healops-incidents.csv'
    anchor.click()
    URL.revokeObjectURL(url)
  }
  const comparison = summary?.performanceComparison
  return (
    <Shell title="Analytics">
      <section className="kpi-grid">
        <KpiCard title="Response improvement" value={comparison ? `${comparison.responseImprovementPercent}%` : '—'} icon={Zap} detail="HealOps vs estimated manual baseline" tone="green"/>
        <KpiCard title="Recovery success" value={summary ? `${summary.successRate}%` : '—'} icon={ShieldCheck} detail="Verified recovery history" tone="cyan"/>
        <KpiCard title="Average anomaly confidence" value={summary?.averageConfidence != null ? `${summary.averageConfidence}%` : '—'} icon={CircleGauge} detail="Isolation Forest observations"/>
        <KpiCard title="Estimated recovery confidence" value={summary?.estimatedRecoverySuccess != null ? `${summary.estimatedRecoverySuccess}%` : '—'} icon={Bot} detail="Score combining anomaly and recovery history" tone="green"/>
      </section>
      <section className="charts-grid"><MetricChart title="CPU utilization" dataKey="cpu" color="#2563eb"/><MetricChart title="Memory utilization" dataKey="memory" color="#6366f1"/></section>
      <section className="comparison-grid">
        <article className="card comparison-card">
          <div className="card-heading"><div><h2>With HealOps AI</h2><p>Measured from the platform</p></div><StatusBadge status="Intelligent response"/></div>
          <div className="comparison-metrics">
            <div><span>AI-assisted response</span><strong>{comparison?.withHealOps?.totalResponseSeconds ? `${comparison.withHealOps.totalResponseSeconds}s` : 'No recovery data yet'}</strong></div>
            <div><span>Recovery success</span><strong>{summary ? `${summary.successRate}%` : '—'}</strong></div>
          </div>
        </article>
        <article className="card comparison-card neutral-comparison">
          <div className="card-heading"><div><h2>Without HealOps AI</h2><p>Estimated manual operating baseline</p></div><StatusBadge status="Estimate"/></div>
          <div className="comparison-metrics">
            <div><span>Manual detection + recovery</span><strong>{comparison ? `${comparison.withoutHealOps.totalResponseSeconds}s` : '35 min'}</strong></div>
            <div><span>Typical manual success</span><strong>Not directly measured</strong></div>
          </div>
        </article>
      </section>
      <section className="bottom-grid">
        <article className="card">
          <div className="card-heading"><div><h2>GreenOps resource efficiency</h2><p>Allocated resources minus measured usage</p></div><StatusBadge status={greenops?.available ? 'Calculated' : 'Unavailable'}/></div>
          {greenops?.available ? (
            <div className="greenops-grid">
              <div><span>Wasted CPU</span><strong>{greenops.wastedCpuCores} cores</strong></div>
              <div><span>Wasted memory</span><strong>{greenops.wastedMemoryGb} GB</strong></div>
              <div><span>Daily energy estimate</span><strong>{greenops.estimatedDailyEnergySavingsKwh} kWh</strong></div>
              <div><span>Monthly CO2 estimate</span><strong>{greenops.estimatedMonthlyCo2SavingsKg} kg</strong></div>
            </div>
          ) : (
            <div className="compact-empty"><CircleGauge size={20}/><span>Waiting for Kubernetes resource requests and Prometheus usage metrics</span></div>
          )}
          {greenops?.method ? <p className="method-note">{greenops.method}</p> : null}
        </article>
        <article className="card">
          <div className="card-heading"><div><h2>Reliability summary</h2><p>Calculated from persisted records</p></div></div>
          <div className="stat-list"><div><span>Incident count</span><strong>{summary?.incidentCount ?? 0}</strong></div><div><span>Recovery success rate</span><strong>{summary ? `${summary.successRate}%` : '—'}</strong></div><div><span>Mean time to recovery</span><strong>{summary?.meanTimeToRecovery ? `${summary.meanTimeToRecovery}s` : '—'}</strong></div></div>
          <button className="primary-button" onClick={exportCsv}>Export incidents CSV</button>
        </article>
      </section>
    </Shell>
  )
}

function SettingsPage() {
  const [settings, setSettings] = useState<any>(null)
  useEffect(() => { getJson<any>('/api/settings').then(setSettings).catch(() => setSettings(null)) }, [])
  async function save() {
    if (!settings) return
    const response = await fetch(`${API}/api/settings`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(settings),
    })
    if (response.ok) setSettings(await response.json())
  }
  return <Shell title="Settings"><section className="settings-grid"><article className="card settings-card"><h2>Cluster connection</h2><label>Prometheus URL<input value={settings?.prometheusUrl ?? ''} onChange={e => setSettings({...settings, prometheusUrl: e.target.value})}/></label><label>Kubernetes context<input value="Current kubeconfig context" readOnly/></label></article><article className="card settings-card"><h2>AI configuration</h2><label>Contamination<input type="number" min="0.01" max="0.5" step="0.01" value={settings?.contamination ?? 0.05} onChange={e => setSettings({...settings, contamination: Number(e.target.value)})}/></label><label>Minimum baseline samples<input type="number" min="10" value={settings?.minBaseline ?? 30} onChange={e => setSettings({...settings, minBaseline: Number(e.target.value)})}/></label></article><article className="card settings-card"><h2>Recovery safety</h2><label className="toggle-row"><span>Automated recovery</span><input type="checkbox" checked={settings?.automatedRecovery ?? false} onChange={e => setSettings({...settings, automatedRecovery: e.target.checked})}/></label><label>Cooldown<input type="number" min="0" value={settings?.cooldown ?? 300} onChange={e => setSettings({...settings, cooldown: Number(e.target.value)})}/></label></article></section><button className="primary-button" style={{margin:'14px 0'}} onClick={save}>Save settings</button></Shell>
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Overview />} />
        <Route path="/monitoring" element={<MonitoringPage />} />
        <Route path="/nodes" element={<NodesPage />} />
        <Route path="/workloads" element={<WorkloadsPage />} />
        <Route path="/ai" element={<AIPage />} />
        <Route path="/incidents" element={<IncidentsPage />} />
        <Route path="/recovery" element={<RecoveryPage />} />
        <Route path="/analytics" element={<AnalyticsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Routes>
    </BrowserRouter>
  )
}
