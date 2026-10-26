


import React, { useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { MapContainer, TileLayer, Marker, Popup, Polyline, useMap } from 'react-leaflet'
import L from 'leaflet'
import { Activity, AlertTriangle, Ambulance, ArrowUpRight, CheckCircle2, ChevronRight, Clock3, Crosshair, FileText, HeartPulse, Hospital, Layers3, MapPin, Plus, Radio, RefreshCw, Route, ShieldCheck, Siren, Users, XCircle, Phone, Building2, Flame, ShieldAlert } from 'lucide-react'
import 'leaflet/dist/leaflet.css'
import './styles.css'

const API = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')
const defaultForm = { report: '', address: 'Connaught Place, New Delhi, India', latitude: '28.6139', longitude: '77.2090', reports: '' }

function iconFor(color) {
  return L.divIcon({ className: 'custom-pin', html: `<span style="background:${color}"></span>`, iconSize: [18,18], iconAnchor: [9,9] })
}
const incidentIcon = iconFor('#fb7185')
const hospitalIcon = iconFor('#34d399')
const stagingIcon = iconFor('#60a5fa')

function FitMap({ points }) {
  const map = useMap()
  useEffect(() => {
    if (points.length > 1) map.fitBounds(points.map(p => [p[0], p[1]]), { padding: [32, 32], maxZoom: 13 })
    else if (points.length === 1) map.setView(points[0], 12)
  }, [map, points])
  return null
}

function MapPanel({ analysis, lat, lon }) {
  const incident = [Number(lat), Number(lon)]
  const hospitals = (analysis?.nearby_hospitals?.hospitals || []).filter(h => Number.isFinite(Number(h.latitude)) && Number.isFinite(Number(h.longitude)))
  const routeCoordinates = analysis?.route?.routes?.[0]?.geometry?.coordinates || []
  const routeLine = routeCoordinates.map(([x,y]) => [y,x])
  const points = [incident, ...hospitals.map(h => [Number(h.latitude), Number(h.longitude)])]
  if (!Number.isFinite(incident[0]) || !Number.isFinite(incident[1])) return <div className="map-placeholder">Enter valid incident coordinates to view the map.</div>
  return <MapContainer center={incident} zoom={11} scrollWheelZoom className="map">
    <TileLayer attribution='&copy; OpenStreetMap contributors' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
    <FitMap points={points}/>
    <Marker position={incident} icon={incidentIcon}><Popup><b>Incident location</b><br/>Coordinates supplied by operator</Popup></Marker>
    {hospitals.map(h => <Marker key={h.id || `${h.latitude}-${h.longitude}`} position={[Number(h.latitude),Number(h.longitude)]} icon={hospitalIcon}><Popup><b>{h.name}</b><br/>{h.distance_km} km straight-line<br/>{h.source}<br/>Availability unconfirmed</Popup></Marker>)}
    {routeLine.length > 1 && <Polyline positions={routeLine} pathOptions={{color:'#60a5fa', weight:5, opacity:.9}}/>}
  </MapContainer>
}

function Pill({children, kind='neutral'}) { return <span className={`pill ${kind}`}>{children}</span> }
function Stat({icon:Icon, label, value, sub}) { return <div className="stat-card"><div className="stat-top"><span className="stat-icon"><Icon size={17}/></span><span>{label}</span></div><strong>{value}</strong><small>{sub}</small></div> }
function SectionTitle({eyebrow, title, action}) { return <div className="section-title"><div><span className="eyebrow">{eyebrow}</span><h2>{title}</h2></div>{action}</div> }

function App() {
  const [health, setHealth] = useState('checking')
  const [form, setForm] = useState(defaultForm)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [incident, setIncident] = useState(null)
  const [analysis, setAnalysis] = useState(null)
  const [mission, setMission] = useState(null)
  const [operator, setOperator] = useState('Demo operator')
  const [decisionNote, setDecisionNote] = useState('')
  const [tab, setTab] = useState('overview')
  const [contacts, setContacts] = useState(null)
  const [contactsOpen, setContactsOpen] = useState(false)
  const [contactsBusy, setContactsBusy] = useState(false)
  const [locationBusy, setLocationBusy] = useState(false)

  async function request(path, options={}) {
    const response = await fetch(`${API}${path}`, { headers: {'Content-Type':'application/json', ...(options.headers || {})}, ...options })
    const body = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(body.detail || body.message || `Request failed (${response.status})`)
    return body
  }

  async function checkHealth() {
    try { await request('/api/health'); setHealth('online') }
    catch { setHealth('offline') }
  }
  useEffect(() => { checkHealth() }, [])

  const priority = analysis?.priority?.priority || analysis?.priority?.level || 'unknown'
  const priorityClass = String(priority).toLowerCase()
  const hospitalCount = analysis?.nearby_hospitals?.count ?? 0
  const route = analysis?.route?.routes?.[0]
  const resourceGaps = analysis?.resources?.resource_gaps || []
  const evidence = analysis?.verification?.verified_facts || []
  const conflicts = analysis?.verification?.conflicting_information || []
  const unknowns = analysis?.verification?.unknown_information || []
  const agentStatuses = useMemo(() => [
    {name:'Incident understanding', icon:FileText, ok:!!analysis?.incident, detail:analysis?.incident?.incident_type || 'Waiting for analysis'},
    {name:'Verification', icon:ShieldCheck, ok:!!analysis?.verification, detail:analysis?.verification?.status || 'Waiting for analysis'},
    {name:'Triage & priority', icon:HeartPulse, ok:!!analysis?.priority, detail:analysis?.priority?.priority || analysis?.priority?.level || 'Waiting for analysis'},
    {name:'Resource planning', icon:Ambulance, ok:!!analysis?.resources, detail:analysis?.resources?.resource_gaps?.length ? `${analysis.resources.resource_gaps.length} resource gaps flagged` : 'Assessment returned'},
    {name:'Route planning', icon:Route, ok:!!analysis?.route?.success, detail:analysis?.route?.success ? `${analysis.route.count || analysis.route.routes?.length || 0} route option(s)` : 'Route unavailable'},
    {name:'Hospital discovery', icon:Hospital, ok:!!analysis?.nearby_hospitals?.success, detail:analysis?.nearby_hospitals?.source || 'No live results'}
  ], [analysis])

  function updateField(key, value) { setForm(prev => ({...prev, [key]:value})) }

  async function searchAddress() {
    if (!form.address.trim()) return
    setLocationBusy(true); setError('')
    try {
      const found = await request('/api/geocode', {method:'POST', body:JSON.stringify({address:form.address.trim()})})
      setForm(prev => ({...prev, latitude:String(found.latitude), longitude:String(found.longitude), address:found.display_name || prev.address}))
    } catch(e) { setError(e.message || 'Could not find that location.') }
    finally { setLocationBusy(false) }
  }

  async function loadEmergencyContacts() {
    if (!incident) return
    setContactsBusy(true); setError('')
    try {
      const result = await request('/api/emergency-contacts', {method:'POST', body:JSON.stringify({
        latitude:Number(form.latitude), longitude:Number(form.longitude),
        incident_type:analysis?.incident?.incident_type || form.report,
        radius:10000
      })})
      setContacts(result); setContactsOpen(true)
    } catch(e) { setError(e.message || 'Unable to load emergency contacts.') }
    finally { setContactsBusy(false) }
  }

  async function submitIncident(event) {
    event.preventDefault()
    setBusy(true); setError(''); setAnalysis(null); setMission(null); setContacts(null); setContactsOpen(false)
    try {
      const reports = form.reports.split('\n').map(s=>s.trim()).filter(Boolean)
      const created = await request('/api/incidents', {method:'POST', body:JSON.stringify({
        report:form.report, latitude:Number(form.latitude), longitude:Number(form.longitude), reports
      })})
      setIncident(created)
      const result = await request(`/api/incidents/${created.id}/analyze`, {method:'POST', body:'{}'})
      setAnalysis(result)
      setTab('overview')
    } catch (e) { setError(e.message || 'Unable to analyze incident.') }
    finally { setBusy(false) }
  }

  async function generateMission() {
    if (!incident?.id) return
    setBusy(true); setError('')
    try { const result = await request(`/api/incidents/${incident.id}/mission`, {method:'POST', body:'{}'}); setMission(result); setTab('mission') }
    catch(e) { setError(e.message) } finally { setBusy(false) }
  }

  async function decide(action) {
    if (!mission?.id) return
    setBusy(true); setError('')
    try {
      const result = await request(`/api/missions/${mission.id}/${action}`, {method:'POST', body:JSON.stringify({operator, note:decisionNote})})
      setMission(result)
    } catch(e) { setError(e.message) } finally { setBusy(false) }
  }

  function loadDemo() {
    setForm({
      report: 'Building collapse reported near Sector 18. Several people may be trapped. One person is reported to have severe bleeding. Debris may be blocking access and the structure may be unstable. Exact number of people affected and current structural safety are unknown.',
      address:'Sector 18, Noida, Uttar Pradesh, India', latitude:'28.5708', longitude:'77.3260',
      reports:'Caller reports a partial building collapse near Sector 18 with people possibly trapped.\nA second witness reports debris blocking the nearest access road and at least one person with severe bleeding.'
    })
    setError('')
  }

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-mark"><Siren size={22}/></div><div><b>RescueMesh<span>AI</span></b><small>EMERGENCY INTELLIGENCE</small></div></div>
      <div className="workspace-label">WORKSPACE</div>
      <button className={`nav-item ${tab==='overview'?'active':''}`} onClick={()=>setTab('overview')}><Layers3 size={17}/> Command center <span className="nav-dot"/></button>
      <button className={`nav-item ${tab==='mission'?'active':''}`} onClick={()=>setTab('mission')}><Radio size={17}/> Mission control</button>
      <button className={`nav-item ${tab==='agents'?'active':''}`} onClick={()=>setTab('agents')}><Activity size={17}/> Agent activity</button>
      <div className="sidebar-spacer"/>
      <div className="sidebar-status"><span className={`status-light ${health}`}/><div><b>API {health==='online'?'connected':health==='checking'?'checking':'offline'}</b><small>{health==='online'?'Backend responding':`Expected at ${API}`}</small></div><button title="Check API" onClick={checkHealth}><RefreshCw size={14}/></button></div>
      <div className="sidebar-footer"><ShieldCheck size={15}/> Human-in-the-loop safety</div>
    </aside>

    <main className="main">
      <header className="topbar"><div><div className="breadcrumb">Operations <ChevronRight size={13}/> <span>{tab==='overview'?'Command center':tab==='mission'?'Mission control':'Agent activity'}</span></div><h1>{tab==='overview'?'Emergency command center':tab==='mission'?'Mission control':'Agent activity'}</h1></div><div className="top-actions"><Pill kind={health==='online'?'success':'warning'}><span className="mini-dot"/> {health==='online'?'SYSTEM ONLINE':health==='checking'?'CONNECTING':'API OFFLINE'}</Pill><div className="avatar">RM</div></div></header>

      <div className="safety-banner"><AlertTriangle size={17}/><div><b>Decision-support prototype</b><span>AI outputs are preliminary. Verify facts, route safety, hospital status and resource availability before action. Nothing is dispatched automatically.</span></div></div>
      {error && <div className="error-banner"><XCircle size={18}/><span>{error}</span><button onClick={()=>setError('')}><XCircle size={15}/></button></div>}

      {tab==='overview' && <div className="dashboard">
        <section className="hero-row"><div><span className="eyebrow">INCIDENT OPERATIONS / LIVE WORKSPACE</span><h2>Turn fragmented signals<br/>into coordinated response.</h2><p>Extract, triage, verify and plan with specialist AI agents — with an operator in control.</p></div><button className="btn secondary" onClick={loadDemo}><FileText size={16}/> Load demo scenario</button></section>
        <div className="stats-grid">
          <Stat icon={Siren} label="Current incident" value={incident?'1':'—'} sub={incident?'Analysis workspace active':'No incident submitted'}/>
          <Stat icon={HeartPulse} label="AI priority" value={priority.toUpperCase()} sub={analysis?'Preliminary triage':'Awaiting incident'}/>
          <Stat icon={Hospital} label="Facility records" value={analysis?hospitalCount:'—'} sub={analysis?.nearby_hospitals?.source || 'Waiting for lookup'}/>
          <Stat icon={Route} label="Recommended route" value={route?`${route.distance_km} km`:'—'} sub={route?`${route.duration_minutes} min estimated drive`:'No route yet'}/>
        </div>

        <div className="content-grid">
          <section className="panel incident-form-panel">
            <SectionTitle eyebrow="NEW RESPONSE" title="Report an incident" action={<Pill>Operator input</Pill>}/>
            <form onSubmit={submitIncident}>
              <label>Incident report <span>Required</span></label>
              <textarea value={form.report} onChange={e=>updateField('report',e.target.value)} placeholder="Describe what happened, hazards, injuries, and any access issues..." required minLength={3} rows={5}/>
              <label>Incident location <span>Enter address or landmark</span></label>
              <div className="location-entry">
                <input value={form.address} onChange={e=>updateField('address',e.target.value)} placeholder="Street address, landmark, city" />
                <button type="button" className="btn secondary" onClick={searchAddress} disabled={locationBusy || health!=='online'}>{locationBusy?<RefreshCw className="spin" size={15}/>:<MapPin size={15}/>} Find location</button>
              </div>
              <div className="field-grid">
                <div><label>Latitude</label><input type="number" step="any" value={form.latitude} onChange={e=>updateField('latitude',e.target.value)} required min="-90" max="90"/></div>
                <div><label>Longitude</label><input type="number" step="any" value={form.longitude} onChange={e=>updateField('longitude',e.target.value)} required min="-180" max="180"/></div>
              </div>
              <label>Additional reports <span>Optional · one per line</span></label>
              <textarea className="reports-input" value={form.reports} onChange={e=>updateField('reports',e.target.value)} placeholder="Add other witness or field reports to compare..." rows={3}/>
              <div className="form-foot"><small><MapPin size={13}/> Search an address above or edit coordinates manually.</small><button className="btn primary" disabled={busy || health!=='online' || !form.report.trim()}>{busy?<><RefreshCw className="spin" size={16}/> Processing</>:<><Activity size={16}/> Analyze incident <ArrowUpRight size={16}/></>}</button></div>
            </form>
          </section>

          <section className="panel map-panel">
            <SectionTitle eyebrow="GEOSPATIAL VIEW" title="Incident & facilities" action={<Pill kind="info"><span className="mini-dot"/> Map</Pill>}/>
            {analysis ? <MapPanel analysis={analysis} lat={form.latitude} lon={form.longitude}/> : <div className="map-empty"><div className="map-empty-icon"><Crosshair size={25}/></div><b>Map ready for your incident</b><span>Submit a report to plot the incident, mapped facilities and available route geometry.</span></div>}
            <div className="map-legend"><span><i className="legend-dot incident-dot"/> Incident</span><span><i className="legend-dot hospital-dot"/> Directory facility</span><span><i className="legend-line"/> OSRM route</span></div>
            {analysis && <button className="btn secondary full emergency-contact-button" onClick={loadEmergencyContacts} disabled={contactsBusy || !incident}>
              {contactsBusy?<RefreshCw className="spin" size={16}/>:<Phone size={16}/>} Emergency Contacts
            </button>}
          </section>
        </div>

        {contactsOpen && contacts && <section className="panel detail-panel contacts-panel">
          <SectionTitle eyebrow="CALL / VERIFY DIRECTLY" title="Emergency contacts" action={<button className="text-btn" onClick={()=>setContactsOpen(false)}><XCircle size={14}/> Close</button>}/>
          <p className="muted">{contacts.message} Local station phone numbers and addresses may be missing if not published in map data.</p>
          <h3 className="contact-group-title"><Building2 size={16}/> Nearby police & fire stations · within {Math.round((contacts.radius_meters||10000)/1000)} km</h3>
          {(contacts.nearby_contacts||[]).length ? <div className="contacts-grid">{contacts.nearby_contacts.map((c,i)=><div className="contact-card" key={c.id||i}>
            <div className="contact-icon">{c.category==='Police'?<ShieldAlert size={18}/>:<Flame size={18}/>}</div><div className="contact-main"><b>{c.name}</b><Pill kind="info">{c.category}</Pill>
            <span><MapPin size={13}/>{c.address||'Address not listed'}</span><span><Phone size={13}/>{c.phone||'Phone number not listed in map data'}</span><small>{c.note}</small></div>
          </div>)}</div> : <p className="empty-small">No mapped police or fire station records returned nearby. Use the national emergency numbers below and verify with local authorities.</p>}
          <h3 className="contact-group-title"><Phone size={16}/> National emergency numbers</h3>
          <div className="contacts-grid">{(contacts.national_contacts||[]).map((c,i)=><div className="contact-card national-contact" key={i}>
            <div className="contact-icon">{c.category==='NDRF'?<ShieldAlert size={18}/>:<Phone size={18}/>}</div><div className="contact-main"><b>{c.name}</b><Pill kind={c.category==='NDRF'?'warning':'info'}>{c.category}</Pill>
            <span><Phone size={13}/><strong>{c.phone}</strong></span><span><MapPin size={13}/>{c.address}</span><small>{c.note}</small></div>
          </div>)}</div>
          <p className="contact-safety-note"><AlertTriangle size={14}/> RescueMesh does not place calls. Confirm contacts and current response availability directly. For immediate danger in India, call 112.</p>
        </section>}

        <div className="content-grid lower-grid">
          <section className="panel">
            <SectionTitle eyebrow="MULTI-AGENT PIPELINE" title="Agent status" action={<button className="text-btn" onClick={()=>setTab('agents')}>View activity <ChevronRight size={14}/></button>}/>
            <div className="agent-list">{agentStatuses.map((a,i)=><div className="agent-row" key={a.name}><div className={`agent-icon ${a.ok?'done':''}`}><a.icon size={17}/></div><div className="agent-copy"><b>{a.name}</b><small>{a.detail}</small></div><Pill kind={a.ok?'success':'neutral'}>{a.ok?'Returned':'Pending'}</Pill></div>)}</div>
          </section>
          <section className="panel">
            <SectionTitle eyebrow="TRIAGE SUMMARY" title="What we know" action={analysis?<Pill kind={priorityClass==='critical'?'danger':'warning'}>{priority.toUpperCase()}</Pill>:null}/>
            {!analysis ? <div className="empty-small">Run an incident analysis to see extracted facts, uncertainty and priority.</div> : <div className="summary-stack">
              <div className="summary-item"><span>Incident type</span><b>{analysis.incident?.incident_type || 'Unknown'}</b></div>
              <div className="summary-item"><span>People at risk</span><b>{analysis.incident?.people_at_risk || 'Unknown'}</b></div>
              <div className="summary-item"><span>Access status</span><b>{analysis.incident?.access_status || 'Unknown'}</b></div>
              <div className="summary-item"><span>Verification</span><b>{analysis.verification?.status || 'Not checked'}</b></div>
              <div className="summary-note"><AlertTriangle size={15}/>{unknowns.length ? unknowns[0] : (analysis.incident?.uncertainties || ['Important facts still require field confirmation.'])[0]}</div>
              <button className="btn primary full" onClick={generateMission} disabled={busy || !!mission}>{mission?'Mission generated':'Generate mission for review'} <ChevronRight size={16}/></button>
            </div>}
          </section>
        </div>

        {analysis && <section className="panel detail-panel"><SectionTitle eyebrow="EVIDENCE & LIMITATIONS" title="Review before decisions"/><div className="evidence-grid"><div><h3><CheckCircle2 size={16}/> Corroborated facts</h3>{evidence.length?evidence.map((x,i)=><p key={i}>{typeof x==='string'?x:JSON.stringify(x)}</p>):<p className="muted">No facts independently verified. Two distinct reports are required for comparison.</p>}</div><div><h3><AlertTriangle size={16}/> Conflicts & unknowns</h3>{[...conflicts,...unknowns].length?[...conflicts,...unknowns].map((x,i)=><p key={i}>{typeof x==='string'?x:JSON.stringify(x)}</p>):<p className="muted">No additional uncertainty was returned by the verification agent.</p>}</div></div></section>}
      </div>}

      {tab==='agents' && <div className="dashboard"><section className="hero-row"><div><span className="eyebrow">TRANSPARENCY</span><h2>Specialists, one mission.</h2><p>Each agent has a bounded role. Missing outputs remain visible instead of being silently invented.</p></div></section><section className="panel"><SectionTitle eyebrow="PIPELINE TRACE" title="Agent activity timeline"/><div className="timeline">{agentStatuses.map((a,i)=><div className="timeline-row" key={a.name}><div className={`timeline-marker ${a.ok?'complete':''}`}>{a.ok?<CheckCircle2 size={16}/>:<Clock3 size={16}/>}</div><div className="timeline-content"><div><b>{a.name}</b><Pill kind={a.ok?'success':'neutral'}>{a.ok?'Completed':'Not run'}</Pill></div><p>{a.detail}</p></div></div>)}</div>{analysis?.agent_errors?.length>0&&<div className="error-list"><b>Agent failures</b>{analysis.agent_errors.map((e,i)=><p key={i}><strong>{e.agent}:</strong> {e.error}</p>)}</div>}{analysis?.duration_seconds!=null&&<div className="latency-note"><Clock3 size={15}/> Pipeline duration: {analysis.duration_seconds}s · AI provider latency may vary.</div>}</section></div>}

      {tab==='mission' && <div className="dashboard"><section className="hero-row"><div><span className="eyebrow">HUMAN APPROVAL GATE</span><h2>Mission control</h2><p>Review the generated plan and record an operator decision. Approval changes the demo mission state only.</p></div>{mission&&<Pill kind={mission.status==='ACTIVE'?'success':mission.status==='REJECTED'?'danger':'warning'}>{mission.status.replaceAll('_',' ')}</Pill>}</section>
        {!mission ? <section className="panel empty-mission"><div className="map-empty-icon"><Radio size={24}/></div><h3>No mission awaiting review</h3><p>Analyze an incident in the command center, then select “Generate mission for review”.</p><button className="btn primary" onClick={()=>setTab('overview')}>Go to command center <ChevronRight size={16}/></button></section> :
          <><section className="panel"><SectionTitle eyebrow={`MISSION ${mission.id.slice(0,8).toUpperCase()}`} title="Rescue mission plan"/><div className="mission-overview"><div><span>Priority</span><b className={`priority-text ${String(mission.priority?.priority||'unknown').toLowerCase()}`}>{String(mission.priority?.priority||'unknown').toUpperCase()}</b></div><div><span>Incident</span><b>{mission.incident?.incident_type||'Unknown incident'}</b></div><div><span>Route</span><b>{mission.route?.routes?.[0]?`${mission.route.routes[0].distance_km} km / ${mission.route.routes[0].duration_minutes} min`:'Unavailable — manual routing required'}</b></div><div><span>Hospital records</span><b>{mission.nearby_hospitals?.count ?? 0} · availability unconfirmed</b></div></div><div className="mission-columns"><div><h3><Ambulance size={17}/> Resource recommendation</h3>{(mission.resources?.required_resources||[]).length?(mission.resources.required_resources).map((r,i)=><div className="resource-row" key={i}><span>{r.resource}</span><b>× {r.quantity}</b><small>{r.reason||'Planning estimate'}</small></div>):<p className="muted">Resource plan unavailable; manual coordination required.</p>}{resourceGaps.length>0&&<div className="warning-inline">Resource gaps were flagged by the agent. Confirm actual inventory before assignment.</div>}</div><div><h3><Hospital size={17}/> Hospital candidates</h3>{(mission.nearby_hospitals?.hospitals||[]).slice(0,5).map(h=><div className="hospital-row" key={h.id}><div><b>{h.name}</b><small>{h.address||'Address not provided'}</small><small>{h.distance_km} km straight-line · {h.source}</small><small><Phone size={11}/> {h.phone || 'Phone number not listed'}</small></div><Pill kind="neutral">Directory listing</Pill></div>)}{!mission.nearby_hospitals?.count&&<p className="muted">No hospital records available. Contact local emergency coordination for verified options.</p>}</div></div></section>
          <section className="panel approval-panel"><SectionTitle eyebrow="OPERATOR DECISION" title="Approve, modify externally, or reject"/><div className="field-grid"><div><label>Operator name</label><input value={operator} onChange={e=>setOperator(e.target.value)} required minLength={2}/></div><div><label>Decision note</label><input value={decisionNote} onChange={e=>setDecisionNote(e.target.value)} placeholder="Add rationale or required changes"/></div></div><div className="approval-actions"><button className="btn danger-outline" disabled={busy||mission.status!=='PENDING_APPROVAL'} onClick={()=>decide('reject')}><XCircle size={16}/> Reject plan</button><button className="btn primary" disabled={busy||mission.status!=='PENDING_APPROVAL'} onClick={()=>decide('approve')}><CheckCircle2 size={16}/> Approve demo mission</button></div><p className="muted tiny">This prototype records a simulated approval state only; it does not dispatch responders.</p></section></>}
      </div>}

      <footer className="app-footer"><span>RescueMesh AI <b>·</b> Hackathon MVP</span><span><ShieldCheck size={14}/> Human approval required <b>·</b> No autonomous dispatch</span></footer>
    </main>
  </div>
}

createRoot(document.getElementById('root')).render(<App/>)
