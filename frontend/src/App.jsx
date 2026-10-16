import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ArrowDownRight, ArrowLeft, ArrowRight, ArrowUpRight, BadgeCheck, Banknote,
  BriefcaseBusiness, Building2, CalendarClock, Check, CheckCircle2, ChevronDown,
  CircleHelp, Clock3, Code2, Compass, FileText, Filter, Github, Gift, Globe2,
  GraduationCap, Info, LayoutDashboard, ListChecks, LoaderCircle, LogOut, Menu,
  Plus, Search, Send, Settings2, ShieldCheck, Sparkles, Target, UploadCloud,
  UserRound, X,
} from 'lucide-react';
import { api } from './api.js';

const ROLE_FALLBACK = [
  { id: 'frontend', label: 'Frontend Developer', openings: 0 },
  { id: 'backend', label: 'Backend Developer', openings: 0 },
  { id: 'fullstack', label: 'Full-Stack Developer', openings: 0 },
  { id: 'data', label: 'Data Analyst / Data Engineer', openings: 0 },
  { id: 'ml', label: 'Machine Learning Engineer', openings: 0 },
  { id: 'devops', label: 'DevOps / Cloud Engineer', openings: 0 },
  { id: 'mobile', label: 'Mobile Developer', openings: 0 },
];

const statusLabel = (value = '') => value.replaceAll('_', ' ').replace(/^./, (letter) => letter.toUpperCase());
const percent = (value) => `${Math.round(Number(value) || 0)}%`;
const initials = (value = 'M') => value.trim().split(/[\s@._-]+/).filter(Boolean).slice(0, 2).map((part) => part[0].toUpperCase()).join('');

function App() {
  const [user, setUser] = useState(() => {
    try { return JSON.parse(localStorage.getItem('matchwork_user') || 'null'); } catch { return null; }
  });
  const [view, setView] = useState(() => {
    try {
      const stored = JSON.parse(localStorage.getItem('matchwork_user') || 'null');
      return stored?.role === 'admin' ? 'admin' : 'overview';
    } catch { return 'overview'; }
  });
  const [analysisId, setAnalysisId] = useState(null);
  const [roles, setRoles] = useState(ROLE_FALLBACK);
  const [notice, setNotice] = useState('');
  const [mobileNav, setMobileNav] = useState(false);
  const [busy, setBusy] = useState(false);
  const [health, setHealth] = useState('checking');

  const refreshRoles = useCallback(async () => {
    try {
      const data = await api.get('/api/roles');
      if (data.roles?.length) setRoles(data.roles);
    } catch { /* The fallback role list keeps the form usable if metadata is temporarily unavailable. */ }
  }, []);

  useEffect(() => {
    if (!user) return;
    refreshRoles();
    api.get('/api/health').then(() => setHealth('online')).catch(() => setHealth('offline'));
  }, [user, refreshRoles]);

  const notify = (message) => {
    setNotice(message);
    window.setTimeout(() => setNotice(''), 4500);
  };

  async function authenticate(mode, values) {
    setBusy(true);
    try {
      const payload = await api.post(`/api/auth/${mode}`, values);
      localStorage.setItem('matchwork_token', payload.access_token);
      localStorage.setItem('matchwork_user', JSON.stringify(payload.user));
      setUser(payload.user);
      setView(payload.user.role === 'admin' ? 'admin' : 'overview');
    } catch (error) { notify(error.message); }
    finally { setBusy(false); }
  }

  function signOut() {
    localStorage.removeItem('matchwork_token');
    localStorage.removeItem('matchwork_user');
    setUser(null);
    setAnalysisId(null);
    setView('overview');
  }

  const openAnalysis = (id) => {
    setAnalysisId(id);
    setView('results');
  };

  if (!user) return <AuthScreen onSubmit={authenticate} busy={busy} notice={notice} />;

  const navItems = user.role === 'admin'
    ? [{ id: 'admin', label: 'Job descriptions', icon: BriefcaseBusiness }]
    : [
        { id: 'overview', label: 'Overview', icon: LayoutDashboard },
        { id: 'new-analysis', label: 'New analysis', icon: Sparkles },
        { id: 'companies', label: 'Company directory', icon: Building2 },
      ];

  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobileNav ? 'sidebar-open' : ''}`}>
        <a className="brand" href="#home" onClick={(event) => { event.preventDefault(); setView(user.role === 'admin' ? 'admin' : 'overview'); }}>
          <span className="brand-mark"><Target size={20} strokeWidth={2.4} /></span>
          <span>matchwork<span className="brand-period">.</span></span>
        </a>
        <div className="workspace-label">WORKSPACE</div>
        <nav className="side-nav" aria-label="Main navigation">
          {navItems.map(({ id, label, icon: Icon }) => (
            <button key={id} className={`nav-item ${view === id ? 'active' : ''}`} onClick={() => { setView(id); setMobileNav(false); }}>
              <Icon size={18} strokeWidth={1.8} /><span>{label}</span>
              {id === 'new-analysis' && <span className="nav-shortcut">NEW</span>}
            </button>
          ))}
        </nav>
        <div className="sidebar-spacer" />
        <div className="sidebar-note">
          <span className="note-icon"><CircleHelp size={16} /></span>
          <div><strong>Thoughtful matching</strong><p>Your resume stays private to your account.</p></div>
        </div>
        <button className="profile-menu" onClick={signOut} title="Sign out">
          <span className="avatar">{initials(user.name || user.email)}</span>
          <span className="profile-copy"><strong>{user.name || user.email.split('@')[0]}</strong><small>{user.role === 'admin' ? 'Administrator' : 'Candidate'}</small></span>
          <LogOut size={17} className="profile-logout" />
        </button>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <button className="icon-button mobile-menu" onClick={() => setMobileNav(!mobileNav)} aria-label="Toggle navigation"><Menu size={20} /></button>
          <div className="breadcrumb"><span>Workspace</span><span className="crumb-slash">/</span><strong>{navItems.find((item) => item.id === view)?.label || (view === 'results' ? 'Your matches' : 'Readiness plan')}</strong></div>
          <div className="topbar-right">
            <span className={`api-status ${health}`}><i />{health === 'online' ? 'API connected' : health === 'offline' ? 'API unavailable' : 'Connecting'}</span>
            <button className="help-button" title="Help and support" aria-label="Help"><CircleHelp size={18} /></button>
            <button className="avatar top-avatar" onClick={signOut} title="Sign out">{initials(user.name || user.email)}</button>
          </div>
        </header>

        <div className="page-wrap">
          {view === 'overview' && user.role !== 'admin' && <Overview user={user} roles={roles} onStart={() => setView('new-analysis')} onOpenAnalysis={openAnalysis} onBrowse={() => setView('companies')} />}
          {view === 'new-analysis' && user.role !== 'admin' && <NewAnalysis roles={roles} onCreated={openAnalysis} onCancel={() => setView('overview')} notify={notify} />}
          {view === 'results' && user.role !== 'admin' && <AnalysisResults analysisId={analysisId} roles={roles} onBack={() => setView('overview')} onReadiness={() => setView('readiness')} notify={notify} />}
          {view === 'readiness' && user.role !== 'admin' && <ReadinessView onBack={() => setView('results')} notify={notify} />}
          {view === 'companies' && user.role !== 'admin' && <CompanyDirectory roles={roles} notify={notify} />}
          {view === 'admin' && user.role === 'admin' && <AdminWorkspace user={user} roles={roles} notify={notify} />}
        </div>
      </main>
      {notice && <div className="toast" role="status"><CircleHelp size={17} />{notice}<button onClick={() => setNotice('')} aria-label="Dismiss"><X size={16} /></button></div>}
    </div>
  );
}

function AuthScreen({ onSubmit, busy, notice }) {
  const [mode, setMode] = useState('login');
  const [showAdminKey, setShowAdminKey] = useState(false);
  const [form, setForm] = useState({ name: '', email: '', password: '', role: 'student', admin_key: '' });
  const update = (key, value) => setForm((current) => ({ ...current, [key]: value }));

  function submit(event) {
    event.preventDefault();
    const payload = mode === 'login'
      ? { email: form.email, password: form.password }
      : { ...form, name: form.name.trim() };
    onSubmit(mode, payload);
  }

  return (
    <div className="auth-shell">
      <section className="auth-story">
        <a className="brand brand-light" href="#home"><span className="brand-mark"><Target size={20} strokeWidth={2.4} /></span><span>matchwork<span className="brand-period">.</span></span></a>
        <div className="story-content">
          <div className="eyebrow light-eyebrow"><span /> CAREER FIT, MADE CLEAR</div>
          <h1>Find work that<br />fits <em>who you are.</em></h1>
          <p>Bring your experience and your work together. See where you stand, what matters next, and which teams need your skills.</p>
          <div className="story-proof"><div className="proof-avatars"><span>AM</span><span>RK</span><span>JS</span><span>+</span></div><span>Built for your next chapter</span><ArrowUpRight size={15} /></div>
        </div>
        <div className="auth-photo" role="img" aria-label="A creative workspace with a laptop and notes" />
        <div className="story-foot"><span>YOUR NEXT MOVE, WITH MORE SIGNAL.</span><span>01 / 03</span></div>
      </section>
      <section className="auth-form-side">
        <div className="auth-form-wrap">
          <div className="auth-top-note"><Globe2 size={15} /> A better way to find your fit</div>
          <h2>{mode === 'login' ? 'Welcome back' : 'Make your next move'}</h2>
          <p className="auth-subtitle">{mode === 'login' ? 'Sign in to pick up where you left off.' : 'Create an account to start finding your fit.'}</p>
          <div className="auth-tabs" role="tablist">
            <button className={mode === 'login' ? 'selected' : ''} onClick={() => setMode('login')} role="tab" aria-selected={mode === 'login'}>Sign in</button>
            <button className={mode === 'register' ? 'selected' : ''} onClick={() => setMode('register')} role="tab" aria-selected={mode === 'register'}>Create account</button>
          </div>
          <form className="auth-form" onSubmit={submit}>
            {mode === 'register' && <label>Your name<input required autoComplete="name" value={form.name} onChange={(event) => update('name', event.target.value)} placeholder="Alex Morgan" /></label>}
            <label>Email address<input required type="email" autoComplete="email" value={form.email} onChange={(event) => update('email', event.target.value)} placeholder="you@example.com" /></label>
            <label>Password<input required minLength={mode === 'register' ? 6 : undefined} type="password" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} value={form.password} onChange={(event) => update('password', event.target.value)} placeholder={mode === 'register' ? 'At least 6 characters' : 'Enter your password'} /></label>
            {mode === 'register' && <>
              <label>Account type<select value={form.role} onChange={(event) => { update('role', event.target.value); setShowAdminKey(event.target.value === 'admin'); }}><option value="student">Candidate</option><option value="admin">Administrator</option></select><ChevronDown className="select-chevron" size={16} /></label>
              {showAdminKey && <label>Admin registration key<input value={form.admin_key} onChange={(event) => update('admin_key', event.target.value)} placeholder="Provided by your operator" /></label>}
            </>}
            <button className="button button-primary auth-submit" disabled={busy}>{busy ? <LoaderCircle className="spin" size={17} /> : <>{mode === 'login' ? 'Sign in to Matchwork' : 'Create your account'}<ArrowRight size={17} /></>}</button>
          </form>
          <div className="auth-privacy"><ShieldCheck size={15} /> Your data is encrypted and only visible to you.</div>
          {notice && <div className="inline-error">{notice}</div>}
        </div>
        <div className="auth-legal">© 2026 Matchwork <span>·</span> Made for meaningful work</div>
      </section>
    </div>
  );
}

function PageHeading({ eyebrow, title, description, action }) {
  return <div className="page-heading"><div><div className="eyebrow"><span />{eyebrow}</div><h1>{title}</h1>{description && <p>{description}</p>}</div>{action}</div>;
}

function Overview({ user, roles, onStart, onOpenAnalysis, onBrowse }) {
  const [analyses, setAnalyses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const load = useCallback(() => api.get('/api/analyses').then((data) => setAnalyses(data.items || [])).catch((err) => setError(err.message)).finally(() => setLoading(false)), []);
  useEffect(() => { load(); }, [load]);
  const doneCount = analyses.filter((item) => item.status === 'done').length;
  const active = analyses.find((item) => ['queued', 'running'].includes(item.status));
  const firstName = (user.name || user.email.split('@')[0]).split(' ')[0];

  return <>
    <PageHeading eyebrow="YOUR CAREER WORKSPACE" title={<>Good to have you, {firstName}<span className="heading-period">.</span></>} description="A clearer view of where your experience can take you next." action={<button className="button button-primary" onClick={onStart}><Plus size={17} /> New analysis</button>} />
    <section className="welcome-banner">
      <div className="welcome-copy"><div className="welcome-kicker"><Sparkles size={15} /> YOUR NEXT OPPORTUNITY STARTS HERE</div><h2>Make your experience<br />work harder for you.</h2><p>Compare your resume and GitHub with real job requirements, then make a plan to close the gaps.</p><button className="button button-lime" onClick={onStart}>Build my match profile <ArrowRight size={17} /></button></div>
      <div className="welcome-graphic" aria-hidden="true"><div className="orbit orbit-one" /><div className="orbit orbit-two" /><div className="orbit-center"><Target size={42} /></div><span className="orbit-tag tag-one"><Code2 size={14} /> skills</span><span className="orbit-tag tag-two"><Github size={14} /> work</span><span className="orbit-tag tag-three"><BriefcaseBusiness size={14} /> roles</span><span className="graphic-star star-one">✳</span><span className="graphic-star star-two">✳</span></div>
    </section>
    <div className="section-heading"><div><h2>Your activity</h2><p>Recent match analyses and progress</p></div><button className="text-button" onClick={load}><span className="refresh-dot" /> Refresh</button></div>
    {active && <button className="processing-callout" onClick={() => onOpenAnalysis(active.id)}><span className="processing-icon"><LoaderCircle size={19} className="spin" /></span><span><strong>Analysis in progress</strong><small>{roles.find((role) => role.id === active.role)?.label || statusLabel(active.role)} · {statusLabel(active.status)}</small></span><ArrowRight size={18} /></button>}
    <div className="stat-grid">
      <StatCard label="Total analyses" value={analyses.length} icon={Sparkles} tone="green" caption="Your career snapshots" />
      <StatCard label="Completed" value={doneCount} icon={BadgeCheck} tone="coral" caption="Ready to explore" />
      <StatCard label="Role paths" value={roles.length} icon={Compass} tone="blue" caption="Career directions" />
    </div>
    <section className="activity-panel">
      <div className="panel-heading"><h3>Recent analyses</h3><span className="panel-count">{analyses.length} total</span></div>
      {loading ? <div className="loading-row"><LoaderCircle className="spin" size={19} /> Loading your workspace</div> : error ? <div className="empty-state"><p>{error}</p></div> : analyses.length ? <div className="analysis-list">{analyses.slice(0, 5).map((item) => <AnalysisRow key={item.id} item={item} roles={roles} onClick={() => onOpenAnalysis(item.id)} />)}</div> : <div className="empty-state"><div className="empty-icon"><FileText size={22} /></div><strong>Your first match is waiting</strong><p>Upload a resume to see which teams and roles line up with your experience.</p><button className="button button-outline" onClick={onStart}>Start an analysis <ArrowRight size={16} /></button></div>}
    </section>
    <div className="bottom-prompt"><span className="prompt-icon"><Building2 size={18} /></span><div><strong>Curious about the companies in your market?</strong><p>Explore teams hiring across your areas of interest.</p></div><button className="text-button" onClick={onBrowse}>Browse directory <ArrowRight size={16} /></button></div>
  </>;
}

function StatCard({ label, value, icon: Icon, tone, caption }) {
  return <div className="stat-card"><span className={`stat-icon ${tone}`}><Icon size={18} /></span><div><span className="stat-label">{label}</span><strong className="stat-value">{value}</strong><span className="stat-caption">{caption}</span></div><ArrowUpRight size={17} className="stat-arrow" /></div>;
}

function AnalysisRow({ item, roles, onClick }) {
  const done = item.status === 'done';
  const failed = item.status === 'failed';
  const role = roles.find((entry) => entry.id === item.role)?.label || statusLabel(item.role);
  return <button className="analysis-row" onClick={onClick}><span className="analysis-symbol"><Target size={18} /></span><span className="analysis-main"><strong>{role}{item.company ? ` · ${item.company}` : ''}</strong><small>{item.resume_filename || 'Resume'}{item.github_username ? ` · @${item.github_username}` : ''}</small></span><span className={`status-pill ${done ? 'status-done' : failed ? 'status-failed' : 'status-pending'}`}><i />{statusLabel(item.status)}</span><span className="analysis-date">{item.created_at ? new Date(item.created_at).toLocaleDateString() : 'Just now'}</span><ArrowRight size={16} className="row-arrow" /></button>;
}

function NewAnalysis({ roles, onCreated, onCancel, notify }) {
  const [role, setRole] = useState('backend');
  const [companyId, setCompanyId] = useState('');
  const [companies, setCompanies] = useState([]);
  const [companiesLoading, setCompaniesLoading] = useState(true);
  const [companiesError, setCompaniesError] = useState('');
  const [github, setGithub] = useState('');
  const [file, setFile] = useState(null);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [roleData, setRoleData] = useState(roles);

  useEffect(() => { setRoleData(roles); }, [roles]);
  useEffect(() => {
    let active = true;
    setCompaniesLoading(true);
    setCompaniesError('');
    api.get(`/api/companies?role=${encodeURIComponent(role)}`)
      .then((data) => { if (active) setCompanies(data.items || []); })
      .catch((err) => { if (active) setCompaniesError(err.message); })
      .finally(() => { if (active) setCompaniesLoading(false); });
    return () => { active = false; };
  }, [role]);
  function acceptFile(candidate) {
    if (!candidate) return;
    if (candidate.type !== 'application/pdf' && !candidate.name.toLowerCase().endsWith('.pdf')) { setError('Please choose a PDF resume.'); return; }
    if (candidate.size > 5 * 1024 * 1024) { setError('This file is larger than the 5 MB upload limit.'); return; }
    setError('');
    setFile(candidate);
  }

  async function submit(event) {
    event.preventDefault();
    if (!file) { setError('Add your resume PDF to continue.'); return; }
    setBusy(true);
    setError('');
    const form = new FormData();
    form.append('role', role);
    if (companyId) form.append('company_id', companyId);
    form.append('github_url', github.trim());
    form.append('resume', file);
    try {
      const result = await api.post('/api/analyses', form);
      notify(`Your ${companyId ? 'company-specific ' : ''}analysis is queued. We will keep this page up to date.`);
      onCreated(result.analysis_id);
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  return <>
    <PageHeading eyebrow="A BETTER MATCH STARTS WITH CONTEXT" title={<>Build your match profile<span>.</span></>} description="Bring your resume and your work. We’ll find the roles that fit what you’ve built." action={<button className="icon-text-button" onClick={onCancel}><ArrowLeft size={16} /> Back to overview</button>} />
    <form className="analysis-form-layout" onSubmit={submit}>
      <div className="form-main-column">
        <div className="analysis-flow" aria-label="Analysis steps">
          <div className="analysis-flow-step"><span>1</span><strong>Choose a role</strong></div>
          <span className="analysis-flow-line" />
          <div className="analysis-flow-step"><span>2</span><strong>Choose a company <small>optional</small></strong></div>
          <span className="analysis-flow-line" />
          <div className="analysis-flow-step"><span>3</span><strong>Add your resume</strong></div>
          <span className="analysis-flow-line" />
          <div className="analysis-flow-step"><span>4</span><strong>Connect GitHub <small>optional</small></strong></div>
          <span className="analysis-flow-line" />
          <div className="analysis-flow-step"><span>5</span><strong>See your matches</strong></div>
        </div>
        <section className="form-section"><div className="form-section-head"><span className="step-index">01</span><div><h2>Choose your direction</h2><p>We’ll weigh skills that matter for the role you’re targeting.</p></div></div>
          <div className="role-grid">{roleData.map((item) => <button type="button" key={item.id} className={`role-option ${role === item.id ? 'chosen' : ''}`} onClick={() => { setRole(item.id); setCompanyId(''); }}><span className="role-check">{role === item.id && <Check size={13} />}</span><span className="role-label">{item.label}</span><span className="role-openings">{item.openings || 0} roles</span></button>)}</div>
        </section>
        <section className="form-section"><div className="form-section-head"><span className="step-index">02</span><div><h2>Target a specific company <span className="optional-label">OPTIONAL</span></h2><p>Choose a company to focus this analysis. Leave it open to compare matches across companies.</p></div></div>
          <label className="company-focus-select" htmlFor="target-company"><Building2 size={19} /><select id="target-company" value={companyId} onChange={(event) => setCompanyId(event.target.value)} disabled={companiesLoading || !!companiesError || !companies.length}><option value="">All companies · show recommended matches</option>{companies.map((company) => <option value={company.id} key={company.id}>{company.name} · {company.ready_jd_count} {company.ready_jd_count === 1 ? 'open role' : 'open roles'}</option>)}</select><ChevronDown size={17} /></label>
          <p className="field-hint" role="status">{companiesLoading ? 'Loading companies hiring for this role…' : companiesError ? 'Company choices are unavailable. You can still compare all companies.' : !companies.length ? 'No processed company listings are available for this role yet.' : companyId ? 'Only roles at this company will be included in your analysis.' : 'You can focus on one company or keep the recommended matches open.'}</p>
        </section>
        <section className="form-section"><div className="form-section-head"><span className="step-index">03</span><div><h2>Add your resume</h2><p>A recent PDF helps us understand your skills and experience.</p></div></div>
          <label className={`upload-zone ${dragging ? 'dragging' : ''} ${file ? 'has-file' : ''}`} onDragOver={(event) => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); acceptFile(event.dataTransfer.files[0]); }}>
            <input type="file" accept="application/pdf,.pdf" onChange={(event) => acceptFile(event.target.files[0])} />
            {file ? <><span className="upload-icon uploaded"><CheckCircle2 size={23} /></span><span className="upload-copy"><strong>{file.name}</strong><small>{(file.size / 1024 / 1024).toFixed(2)} MB · PDF document</small></span><button type="button" className="icon-button remove-file" onClick={(event) => { event.preventDefault(); setFile(null); }} aria-label="Remove resume"><X size={17} /></button></> : <><span className="upload-icon"><UploadCloud size={23} /></span><span className="upload-copy"><strong>Drop your resume here, or <em>browse files</em></strong><small>PDF only · Up to 5 MB</small></span></>}
          </label>
        </section>
        <section className="form-section"><div className="form-section-head"><span className="step-index">04</span><div><h2>Connect your GitHub <span className="optional-label">OPTIONAL</span></h2><p>Project evidence can make your skills stand out more clearly.</p></div></div>
          <label className="input-with-icon"><Github size={18} /><input type="url" value={github} onChange={(event) => setGithub(event.target.value)} placeholder="https://github.com/your-username" /></label>
          <div className="field-hint"><ShieldCheck size={14} /> Public profile and repositories only. You can skip this.</div>
        </section>
        {error && <div className="form-error"><CircleHelp size={16} />{error}</div>}
        <div className="form-actions"><button type="button" className="button button-quiet" onClick={onCancel}>Cancel</button><button className="button button-primary" disabled={busy}>{busy ? <><LoaderCircle className="spin" size={17} /> Starting analysis</> : <>Find my matches <ArrowRight size={17} /></>}</button></div>
      </div>
      <aside className="analysis-aside"><div className="aside-topline"><Sparkles size={17} /> WHAT YOU’LL GET</div><h3>More than a score.</h3><p>A practical picture of how your experience lines up with real opportunities.</p><div className="aside-benefit"><span><Target size={17} /></span><div><strong>Ranked role matches</strong><small>See your strongest company fits first.</small></div></div><div className="aside-benefit"><span><Code2 size={17} /></span><div><strong>Evidence that matters</strong><small>Compare resume and GitHub signals.</small></div></div><div className="aside-benefit"><span><ArrowDownRight size={17} /></span><div><strong>A path to close gaps</strong><small>Get focused steps for a role you choose.</small></div></div><div className="aside-rule" /><div className="aside-foot"><ShieldCheck size={16} /><span>Your resume is processed privately and results are only visible to you.</span></div></aside>
    </form>
  </>;
}

function AnalysisResults({ analysisId, roles, onBack, onReadiness, notify }) {
  const [analysis, setAnalysis] = useState(null);
  const [matches, setMatches] = useState(null);
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [detail, setDetail] = useState(null);
  const [busyReadiness, setBusyReadiness] = useState(false);

  const loadAnalysis = useCallback(async () => {
    if (!analysisId) { setError('Choose an analysis from your activity to see results.'); setLoading(false); return; }
    try {
      const data = await api.get(`/api/analyses/${analysisId}`);
      setAnalysis(data);
      if (data.status === 'done') {
        const results = await api.get(`/api/analyses/${analysisId}/matches`);
        setMatches(results);
        setError('');
      } else if (data.status === 'failed') setError(data.error || 'This analysis could not be completed.');
    } catch (err) {
      setError(err.message);
      if (err.status === 401) localStorage.removeItem('matchwork_token');
    } finally { setLoading(false); }
  }, [analysisId]);

  useEffect(() => { loadAnalysis(); }, [loadAnalysis]);
  useEffect(() => {
    if (!analysis || !['queued', 'running'].includes(analysis.status)) return undefined;
    const timer = window.setInterval(loadAnalysis, 2500);
    return () => window.clearInterval(timer);
  }, [analysis, loadAnalysis]);

  useEffect(() => {
    if (!matches?.items?.length || selected) return;
    const first = matches.items[0];
    setSelected(first);
    api.get(`/api/analyses/${analysisId}/matches/${first.jd_id}`).then(setDetail).catch(() => {});
  }, [matches, analysisId, selected]);

  async function selectMatch(item) {
    setSelected(item);
    setDetail(null);
    try { setDetail(await api.get(`/api/analyses/${analysisId}/matches/${item.jd_id}`)); }
    catch (err) { notify(err.message); }
  }

  async function startReadiness() {
    if (!selected) return;
    setBusyReadiness(true);
    try {
      const report = await api.post(`/api/analyses/${analysisId}/readiness`, { jd_id: selected.jd_id });
      sessionStorage.setItem('matchwork_readiness', JSON.stringify(report));
      onReadiness();
    } catch (err) { notify(err.message); }
    finally { setBusyReadiness(false); }
  }

  if (loading && !analysis) return <LoadingPage label="Loading your analysis" />;
  const isPending = analysis && ['queued', 'running'].includes(analysis.status);
  if (isPending) return <>
    <PageHeading eyebrow="MATCH ANALYSIS" title={<>Putting the pieces together<span>.</span></>} description="Your resume and role signals are being compared with open opportunities." action={<button className="icon-text-button" onClick={onBack}><ArrowLeft size={16} /> All activity</button>} />
    <div className="progress-layout"><section className="progress-card"><div className="progress-orb"><LoaderCircle size={34} className="spin" /></div><div className="eyebrow"><span /> ANALYSIS IN PROGRESS</div><h2>Finding the right signal.</h2><p>This usually takes under a minute. You can stay here while each step finishes.</p><div className="progress-steps">{Object.entries(analysis.progress || {}).map(([key, value], index) => <div className={`progress-step ${value === 'done' ? 'step-done' : value === 'running' ? 'step-active' : ''}`} key={key}><span className="progress-step-icon">{value === 'done' ? <Check size={14} /> : value === 'running' ? <LoaderCircle size={14} className="spin" /> : String(index + 1).padStart(2, '0')}</span><span>{({ resume: 'Reading your resume', github: 'Reviewing your GitHub', profile: 'Building your skill profile', matching: 'Comparing role requirements', explanation: 'Preparing your results' })[key] || statusLabel(key)}</span><small>{statusLabel(value)}</small></div>)}</div><button className="text-button" onClick={loadAnalysis}>Check status <ArrowRight size={15} /></button></section><aside className="progress-note"><div className="note-icon large"><Clock3 size={19} /></div><h3>Built around real evidence</h3><p>We compare the skills and project signals in your profile against the requirements each team has shared.</p><div className="note-mini"><span>ROLE</span><strong>{roles.find((role) => role.id === analysis.role)?.label || statusLabel(analysis.role)}</strong></div></aside></div>
  </>;
  if (error && !matches) return <><PageHeading eyebrow="MATCH ANALYSIS" title={<>We hit a snag<span>.</span></>} action={<button className="icon-text-button" onClick={onBack}><ArrowLeft size={16} /> All activity</button>} /><div className="empty-state error-state"><div className="empty-icon"><CircleHelp size={22} /></div><strong>{error}</strong><p>{analysis?.warnings?.length ? analysis.warnings.join(' · ') : 'Try again or start a fresh analysis with a different resume.'}</p><button className="button button-outline" onClick={loadAnalysis}>Try again <ArrowRight size={16} /></button></div></>;
  if (!matches) return <><PageHeading eyebrow="MATCH ANALYSIS" title={<>Your matches<span>.</span></>} action={<button className="icon-text-button" onClick={onBack}><ArrowLeft size={16} /> All activity</button>} /><div className="empty-state"><strong>No analysis selected</strong><p>Start a new analysis or choose one from your recent activity.</p><button className="button button-primary" onClick={onBack}>Back to overview</button></div></>;

  return <>
    <PageHeading eyebrow="YOUR MATCH PROFILE" title={<>A good fit starts here<span>.</span></>} description={`${matches.company ? `Company focus: ${matches.company} · ` : ''}${roles.find((role) => role.id === matches.role)?.label || statusLabel(matches.role)} · ${matches.total_scored} roles compared`} action={<button className="icon-text-button" onClick={onBack}><ArrowLeft size={16} /> All activity</button>} />
    {analysis?.warnings?.length > 0 && <div className="warning-banner"><CircleHelp size={17} /><span>{analysis.warnings.join(' · ')}</span></div>}
    <div className="results-layout"><section className="matches-column"><div className="results-caption"><div><h2>Your strongest matches</h2><p>Ranked by how your experience lines up with each role.</p></div><span className="result-count">TOP {matches.items.length}</span></div>
      {matches.items.map((item, index) => <MatchCard key={item.jd_id} item={item} index={index} selected={selected?.jd_id === item.jd_id} onClick={() => selectMatch(item)} />)}
      {!matches.items.length && <div className="empty-state"><strong>No matches yet</strong><p>There are no processed job descriptions for this role.</p></div>}
      <div className="match-disclaimer"><ShieldCheck size={15} /> Scores are a guide to help you focus, not a hiring decision.</div>
    </section>
    <aside className="match-detail-panel">{selected && detail ? <><div className="detail-company-head"><span className="company-monogram">{initials(selected.company)}</span><div><span className="detail-eyebrow">ROLE FIT · #{selected.rank}</span><h2>{selected.company}</h2><p>{selected.title}</p></div><button className="icon-button detail-open" title="Open company website" aria-label="Company details"><ArrowUpRight size={17} /></button></div><div className="score-overview"><div className="score-ring" style={{ '--score': `${selected.overall_score}%` }}><div><strong>{Math.round(selected.overall_score)}</strong><small>FIT</small></div></div><div><span className="fit-label">OVERALL MATCH</span><strong className="fit-copy">A promising alignment</strong><small className="fit-muted">Based on skills, experience &amp; evidence</small></div></div><div className="score-breakdown"><div><span>Resume fit</span><strong>{percent(selected.resume_score)}</strong><div className="score-track"><i style={{ width: `${selected.resume_score}%` }} /></div></div><div><span>GitHub fit</span><strong>{selected.github_score == null ? 'Not connected' : percent(selected.github_score)}</strong><div className="score-track"><i className="github-track" style={{ width: `${selected.github_score || 0}%` }} /></div></div></div><div className="detail-divider" />
      <div className="detail-list"><div className="detail-list-heading"><CheckCircle2 size={16} /><strong>Where you align</strong></div>{(detail.breakdown?.skill_match?.matched || []).slice(0, 5).map((skill) => <span className="skill-chip matched" key={skill}><Check size={12} />{skill}</span>)}{!detail.breakdown?.skill_match?.matched?.length && <p className="detail-muted">Your skills are being mapped to this role.</p>}</div>
      {!!detail.breakdown?.skill_match?.missing_must?.length && <div className="detail-list"><div className="detail-list-heading missing-heading"><ArrowDownRight size={16} /><strong>Worth building next</strong></div><div className="skill-chip-list">{detail.breakdown.skill_match.missing_must.slice(0, 5).map((skill) => <span className="skill-chip missing" key={skill}>{skill}</span>)}</div></div>}
      {selected.summary && <blockquote className="match-summary">“{selected.summary}”</blockquote>}
      <button className="button button-primary full-button" onClick={startReadiness} disabled={busyReadiness}>{busyReadiness ? <LoaderCircle className="spin" size={17} /> : <><Sparkles size={16} /> Build my readiness plan <ArrowRight size={16} /></>}</button>
      <p className="readiness-caption">A practical, score-free plan for this specific role.</p>
    </> : <div className="detail-loading"><LoaderCircle className="spin" size={22} /><span>Loading role details</span></div>}</aside></div>
  </>;
}

function MatchCard({ item, index, selected, onClick }) {
  return <button className={`match-card ${selected ? 'match-selected' : ''}`} onClick={onClick}><span className={`rank-badge rank-${index + 1}`}>{String(item.rank).padStart(2, '0')}</span><span className="match-card-main"><span className="match-role-line">{item.role_family || 'Software'} · {item.seniority || 'Open level'}</span><strong>{item.company}</strong><span className="match-title">{item.title}</span><span className="match-tags">{(item.strengths || []).slice(0, 2).map((strength) => <span key={strength}>{strength.split(/[.,]/)[0]}</span>)}</span></span><span className="match-score-side"><span className="score-mini" style={{ '--score': `${item.overall_score}%` }}><strong>{Math.round(item.overall_score)}</strong></span><small>match</small><ArrowRight size={16} className="match-arrow" /></span></button>;
}

function ReadinessView({ onBack, notify }) {
  const [report, setReport] = useState(() => {
    try { return JSON.parse(sessionStorage.getItem('matchwork_readiness') || 'null'); } catch { return null; }
  });
  const [feedback, setFeedback] = useState('');
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [analysisId, setAnalysisId] = useState(null);

  useEffect(() => {
    if (!report?.analysis_id) return;
    setAnalysisId(report.analysis_id);
  }, [report]);

  async function sendFeedback(helpful) {
    if (!analysisId || !report?.jd_id) { setSent(true); return; }
    setBusy(true);
    try { await api.post(`/api/analyses/${analysisId}/feedback`, { analysis_id: analysisId, jd_id: report.jd_id, helpful, comment: feedback }); setSent(true); }
    catch (error) { notify(error.message); }
    finally { setBusy(false); }
  }

  if (!report) return <><PageHeading eyebrow="READINESS PLAN" title={<>Your next steps<span>.</span></>} action={<button className="icon-text-button" onClick={onBack}><ArrowLeft size={16} /> Back to matches</button>} /><div className="empty-state"><strong>No plan to show yet</strong><p>Choose a role match and build a readiness plan to see your next steps.</p><button className="button button-primary" onClick={onBack}>View matches <ArrowRight size={16} /></button></div></>;

  return <>
    <PageHeading eyebrow="YOUR ROLE READINESS" title={<>Turn a strong fit into a plan<span>.</span></>} description={`${report.job_title || 'Your selected role'} · ${report.company || 'Company match'}`} action={<button className="icon-text-button" onClick={onBack}><ArrowLeft size={16} /> Back to matches</button>} />
    <div className="readiness-banner"><div className="readiness-emblem"><Target size={25} /></div><div><span>YOUR READINESS OUTLOOK</span><h2>{report.status || 'A focused path forward'}</h2><p>No score, just a practical read on the work ahead.</p></div><div className="plan-stamp"><span>PERSONALIZED</span><Sparkles size={17} /></div></div>
    <div className="readiness-grid"><section className="readiness-main">
      <div className="readiness-section"><div className="readiness-section-head"><span className="readiness-icon strength"><CheckCircle2 size={17} /></span><div><h2>What’s already working</h2><p>Your strongest signals for this role</p></div></div><div className="strength-list">{(report.strengths || []).map((item, index) => <div className="strength-item" key={`${item}-${index}`}><Check size={14} /><span>{item}</span></div>)}</div></div>
      <div className="readiness-section"><div className="readiness-section-head"><span className="readiness-icon improve"><ArrowUpRight size={17} /></span><div><h2>Where to focus next</h2><p>High-value ways to improve your profile</p></div></div><div className="suggestion-list">{(report.suggestions_to_improve || []).map((item, index) => <div className="suggestion-item" key={`${item}-${index}`}><span>{String(index + 1).padStart(2, '0')}</span><p>{item}</p></div>)}</div></div>
      {!!report.gaps?.length && <div className="readiness-section"><div className="readiness-section-head"><span className="readiness-icon gap"><Filter size={16} /></span><div><h2>Skill signals</h2><p>How your evidence maps to the requirements</p></div></div><div className="gap-table"><div className="gap-header"><span>SKILL</span><span>REQUIREMENT</span><span>YOUR EVIDENCE</span></div>{report.gaps.slice(0, 8).map((gap) => <div className="gap-row" key={gap.skill}><strong>{gap.skill}</strong><span className={`requirement-tag ${gap.requirement === 'must' ? 'required' : ''}`}>{gap.requirement === 'must' ? 'Must have' : 'Nice to have'}</span><span className="evidence-state"><i className={`evidence-dot ${gap.you_have}`} />{statusLabel(gap.you_have)}</span></div>)}</div></div>}
      {!!report.interview_topics?.length && <div className="readiness-section"><div className="readiness-section-head"><span className="readiness-icon interview"><GraduationCap size={17} /></span><div><h2>Interview prep</h2><p>Topics worth getting comfortable with</p></div></div><div className="topic-list">{report.interview_topics.map((topic, index) => <span key={`${topic}-${index}`}>{topic}</span>)}</div></div>}
    </section><aside className="plan-column"><div className="plan-column-heading"><span><Clock3 size={17} /></span><div><h2>Your action plan</h2><p>Small steps, meaningful progress</p></div></div><div className="timeline">{(report.next_steps || []).map((step, index) => <div className="timeline-item" key={`${step.week}-${step.focus}`}><div className="timeline-marker">{String(step.week || index + 1).padStart(2, '0')}</div><div className="timeline-content"><span>WEEK {step.week || index + 1}</span><h3>{step.focus}</h3><ul>{(step.actions || []).map((action, actionIndex) => <li key={`${action}-${actionIndex}`}>{action}</li>)}</ul></div></div>)}</div><div className="plan-quote"><span>“</span><p>Progress is built one proof point at a time.</p></div></aside></div>
    <section className="feedback-bar"><div><h3>Was this plan useful?</h3><p>Your feedback helps us make the guidance more relevant.</p></div>{sent ? <span className="feedback-thanks"><CheckCircle2 size={17} /> Thanks for sharing</span> : <div className="feedback-actions"><input value={feedback} onChange={(event) => setFeedback(event.target.value)} placeholder="Optional note" aria-label="Optional feedback note" /><button className="feedback-button" disabled={busy} onClick={() => sendFeedback(true)} title="This was useful" aria-label="This was useful"><Check size={17} /></button><button className="feedback-button" disabled={busy} onClick={() => sendFeedback(false)} title="This needs improvement" aria-label="This needs improvement"><X size={17} /></button></div>}</section>
  </>;
}

function CompanyDirectory({ roles, notify }) {
  const [companies, setCompanies] = useState([]);
  const [query, setQuery] = useState('');
  const [role, setRole] = useState('');
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const [companyDetail, setCompanyDetail] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    api.get(`/api/companies?${new URLSearchParams({ ...(role ? { role } : {}), ...(query.trim() ? { q: query.trim() } : {}) })}`).then((data) => { if (active) setCompanies(data.items || []); }).catch((err) => { if (active) setError(err.message); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [role, query]);

  async function viewCompany(company) {
    setSelected(company);
    setCompanyDetail(null);
    try { setCompanyDetail(await api.get(`/api/companies/${company.id}`)); }
    catch (err) { notify(err.message); }
  }

  return <>
    <PageHeading eyebrow="THE PEOPLE BEHIND THE ROLES" title={<>Find your kind of team<span>.</span></>} description="Explore companies by the skills and roles they’re hiring for." />
    <div className="directory-toolbar"><label className="search-box"><Search size={18} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search companies" /><kbd>⌘ K</kbd></label><label className="role-filter"><Filter size={16} /><select value={role} onChange={(event) => setRole(event.target.value)}><option value="">All role families</option>{roles.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select><ChevronDown size={15} /></label><span className="directory-count">{companies.length} {companies.length === 1 ? 'company' : 'companies'}</span></div>
    {error ? <div className="empty-state error-state"><strong>{error}</strong><p>Check your connection and try again.</p></div> : loading ? <LoadingPage label="Finding companies" /> : <div className="company-grid">{companies.map((company, index) => <button className="company-card" key={company.id} onClick={() => viewCompany(company)}><div className="company-card-head"><span className={`company-monogram company-color-${index % 5}`}>{initials(company.name)}</span><span className="company-card-arrow"><ArrowUpRight size={17} /></span></div><h3>{company.name}</h3><p>{company.industry || company.location || 'Company profile'}</p><div className="company-metrics"><span><BriefcaseBusiness size={14} />{company.ready_jd_count || 0} open roles</span>{company.location && <span><Globe2 size={14} />{company.location}</span>}</div><div className="company-role-tags">{Object.keys(company.roles || {}).slice(0, 3).map((key) => <span key={key}>{roles.find((item) => item.id === key)?.label?.split(' ')[0] || statusLabel(key)}</span>)}</div></button>)}</div>}
    {!loading && !error && !companies.length && <div className="empty-state"><div className="empty-icon"><Building2 size={22} /></div><strong>No companies match those filters</strong><p>Try a broader search or choose another role family.</p><button className="text-button" onClick={() => { setRole(''); setQuery(''); }}>Clear filters <X size={15} /></button></div>}
    {selected && <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setSelected(null); }}><section className="company-modal" role="dialog" aria-modal="true" aria-label={`${selected.name} company details`}><button className="modal-close icon-button" onClick={() => setSelected(null)} aria-label="Close company details"><X size={18} /></button>{companyDetail ? <><div className="modal-company-heading"><span className="company-monogram">{initials(companyDetail.name)}</span><div><span className="detail-eyebrow">COMPANY PROFILE</span><h2>{companyDetail.name}</h2><p>{companyDetail.industry || 'Industry not listed'}{companyDetail.location ? ` · ${companyDetail.location}` : ''}</p></div></div><div className="modal-stats"><span><strong>{companyDetail.ready_jd_count || 0}</strong><small>Open roles</small></span><span><strong>{Object.keys(companyDetail.roles || {}).length}</strong><small>Role families</small></span><span><strong>{companyDetail.locations?.length || 0}</strong><small>Locations</small></span></div><h3 className="modal-subhead">Hiring signals</h3><div className="topic-list">{(companyDetail.top_skills || []).slice(0, 8).map((item) => <span key={item.skill}>{item.skill}</span>)}</div><h3 className="modal-subhead">Available roles</h3><div className="modal-jobs">{(companyDetail.job_descriptions || []).length ? companyDetail.job_descriptions.map((job) => <div className="modal-job" key={job.id}><span><strong>{job.title || 'Open position'}</strong><small>{job.role_family || 'Role family not specified'} · {job.seniority || 'Level not specified'}</small></span><ArrowUpRight size={16} /></div>) : <p className="detail-muted">No active roles listed yet.</p>}</div>{companyDetail.website && <a className="button button-outline full-button company-website" href={companyDetail.website} target="_blank" rel="noreferrer">Visit company <ArrowUpRight size={16} /></a>}</> : <div className="detail-loading"><LoaderCircle className="spin" size={22} /><span>Loading company details</span></div>}</section></div>}
  </>;
}

const EMPTY_JD_FORM = {
  company_name: '', title: '', role_family: '', website: '', location: '', industry: '',
  employment_type: '', compensation: '', work_mode: '', duration: '', conversion: '',
  eligibility: '', selection_process: '', perks: '', about: '',
  raw_text: '',
};

const splitList = (value = '') => value.split(/\n|,|;/).map((part) => part.trim()).filter(Boolean);

function AdminWorkspace({ roles, notify }) {
  const [stats, setStats] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [parsing, setParsing] = useState(false);
  const [form, setForm] = useState({ ...EMPTY_JD_FORM });
  const [filter, setFilter] = useState('');
  const [error, setError] = useState('');
  const [file, setFile] = useState(null);
  const [fileInfo, setFileInfo] = useState('');
  const [parseStrategy, setParseStrategy] = useState('');
  const [detail, setDetail] = useState(null);
  const [detailData, setDetailData] = useState(null);
  const fileInputRef = useRef(null);

  const loadAdminData = useCallback(async () => {
    setLoading(true);
    try {
      const [statData, jobData] = await Promise.all([api.get('/api/admin/stats'), api.get(`/api/admin/jds?limit=40${filter ? `&status=${filter}` : ''}`)]);
      setStats(statData);
      setJobs(jobData.items || []);
      setError('');
    } catch (err) { setError(err.message); }
    finally { setLoading(false); }
  }, [filter]);

  useEffect(() => { loadAdminData(); }, [loadAdminData]);

  function acceptFile(candidate) {
    if (!candidate) return;
    if (candidate.type !== 'application/pdf' && !/\.pdf$/i.test(candidate.name)) {
      setError('Please choose a PDF file.');
      return;
    }
    setError('');
    setFile(candidate);
    setFileInfo(`${candidate.name} · waiting to parse`);
  }

  async function runParse() {
    if (!file) { setError('Choose a PDF file first.'); return; }
    setParsing(true);
    setError('');
    try {
      const fd = new FormData();
      fd.append('file', file);
      const result = await api.post('/api/admin/jds/parse', fd);
      const s = result.structured || {};
      setForm({
        company_name: s.company || '', title: s.title || '', role_family: s.role_family || '',
        website: '', location: s.location || '', industry: s.industry || '',
        employment_type: s.employment_type || '', compensation: s.compensation || '',
        work_mode: s.work_mode || '', duration: s.duration || '',
        conversion: s.conversion || '', eligibility: s.eligibility || '',
        selection_process: (s.selection_process || []).join('\n'),
        perks: (s.perks || []).join('\n'),
        about: s.about || '',
        raw_text: result.raw_text || '',
      });
      setParseStrategy(result.strategy || '');
      setFileInfo(`${file.name} · ${result.strategy === 'llm' ? 'AI extraction' : 'fallback extraction'} complete`);
      notify(result.strategy === 'llm' ? 'Company and role details detected from the PDF — review, then save.' : 'Company and role details filled in — fine-tune them, then save.');
    } catch (err) { setError(err.message); }
    finally { setParsing(false); }
  }

  async function createJob(event) {
    event.preventDefault();
    if (!form.raw_text.trim()) { setError('Job description text is required.'); return; }
    setSubmitting(true);
    setError('');
    try {
      const body = {
        company_name: form.company_name.trim(),
        title: form.title.trim() || null,
        raw_text: form.raw_text,
        role_family: form.role_family || null,
        website: form.website.trim() || null,
        location: form.location.trim() || null,
        industry: form.industry.trim() || null,
        employment_type: form.employment_type.trim() || null,
        compensation: form.compensation.trim() || null,
        work_mode: form.work_mode.trim() || null,
        duration: form.duration.trim() || null,
        conversion: form.conversion.trim() || null,
        eligibility: form.eligibility.trim() || null,
        selection_process: splitList(form.selection_process),
        perks: splitList(form.perks),
        about: form.about.trim() || null,
      };
      const result = await api.post('/api/admin/jds', body);
      setForm({ ...EMPTY_JD_FORM });
      setFile(null);
      setFileInfo('');
      setParseStrategy('');
      notify(`Job description queued for processing (#${result.jd_id}).`);
      loadAdminData();
    } catch (err) { setError(err.message); }
    finally { setSubmitting(false); }
  }

  async function reprocess(id) {
    try { await api.post(`/api/admin/jds/${id}/reprocess`, {}); notify('Job description queued for reprocessing.'); loadAdminData(); }
    catch (err) { notify(err.message); }
  }

  async function archive(id) {
    try { const response = await api.delete(`/api/admin/jds/${id}`); notify(response.archived ? 'Referenced job description archived.' : 'Job description deleted.'); loadAdminData(); }
    catch (err) { notify(err.message); }
  }

  async function viewJob(job) {
    setDetail(job);
    setDetailData(null);
    try { setDetailData(await api.get(`/api/admin/jds/${job.id}`)); }
    catch (err) { notify(err.message); }
  }

  return <>
    <PageHeading eyebrow="ADMINISTRATION" title={<>Keep opportunity data useful<span>.</span></>} description="Upload a JD to auto-detect every company and role detail, then save it to matching." action={<button className="button button-outline" onClick={loadAdminData}><Settings2 size={16} /> Refresh data</button>} />
    {error && <div className="warning-banner"><CircleHelp size={17} /><span>{error}</span></div>}
    <div className="admin-stats">{[['Companies', stats?.companies ?? '—', Building2], ['Job descriptions', stats?.job_descriptions ?? '—', BriefcaseBusiness], ['Candidates', stats?.users ?? '—', UserRound], ['Analyses', stats?.analyses ?? '—', Target]].map(([label, value, Icon]) => <div className="admin-stat" key={label}><span><Icon size={17} /></span><div><small>{label}</small><strong>{value}</strong></div></div>)}</div>
    <div className="admin-layout"><section className="admin-form-card">
      <div className="admin-form-heading"><span className="form-icon"><Plus size={17} /></span><div><h2>Add a job description</h2><p>Drop in a JD PDF and the company and role details are detected automatically — or paste the text and let the pipeline fill the rest.</p></div></div>
      <div className="upload-zone" role="button" tabIndex={0} onClick={() => fileInputRef.current?.click()} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); fileInputRef.current?.click(); } }}>
        <input ref={fileInputRef} type="file" accept="application/pdf" hidden onChange={(event) => acceptFile(event.target.files?.[0])} />
        {parsing ? <><LoaderCircle size={20} className="spin" /><span>Reading job description…</span></> : file ? <><FileText size={20} /><span className="upload-filename">{fileInfo}</span>{!parseStrategy && <small>Scanning the PDF fills the form below.</small>}<button className="text-button" onClick={(event) => { event.stopPropagation(); setFile(null); setFileInfo(''); setParseStrategy(''); }}>Remove file <X size={14} /></button></> : <><UploadCloud size={20} /><strong>Upload a JD PDF</strong><span>Company, title, skills, salary and more are detected automatically.</span></>}
      </div>
      {file && !parseStrategy && <button className="button button-primary upload-detect" onClick={runParse} disabled={parsing}>{parsing ? <LoaderCircle className="spin" size={17} /> : <><Sparkles size={16} /> Detect all JD details</>}</button>}
      {parseStrategy && <div className="parse-hint"><CheckCircle2 size={15} /> Fields detected from <strong>{file?.name}</strong> — review them below, then save.<button className="text-button" onClick={() => { setFile(null); setFileInfo(''); setParseStrategy(''); }}>Clear <X size={14} /></button></div>}
      <form className="admin-form" onSubmit={createJob}>
        <div className="admin-form-row"><label>Company name<input required maxLength={255} value={form.company_name} onChange={(event) => setForm({ ...form, company_name: event.target.value })} placeholder="Acme, Inc." /></label><label>Job title<input value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} placeholder="Backend Engineer" /></label></div>
        <div className="admin-form-row"><label>Employment type<select value={form.employment_type} onChange={(event) => setForm({ ...form, employment_type: event.target.value })}><option value="">Auto-detect</option><option value="internship">Internship</option><option value="full-time">Full-time</option><option value="part-time">Part-time</option><option value="contract">Contract</option><option value="apprenticeship">Apprenticeship</option><option value="fellowship">Fellowship</option></select></label><label>Work mode<select value={form.work_mode} onChange={(event) => setForm({ ...form, work_mode: event.target.value })}><option value="">Auto-detect</option><option value="remote">Remote</option><option value="hybrid">Hybrid</option><option value="onsite">Onsite</option></select></label></div>
        <div className="admin-form-row"><label>Duration<input value={form.duration} onChange={(event) => setForm({ ...form, duration: event.target.value })} placeholder="6 months" /></label><label>Conversion opportunity<input value={form.conversion} onChange={(event) => setForm({ ...form, conversion: event.target.value })} placeholder="Full-time conversion on successful completion" /></label></div>
        <div className="admin-form-row"><label>Compensation<input value={form.compensation} onChange={(event) => setForm({ ...form, compensation: event.target.value })} placeholder="₹10,000 / month stipend · one-time bonus" /></label></div>
        <div className="admin-form-row"><label>Role family<select value={form.role_family} onChange={(event) => setForm({ ...form, role_family: event.target.value })}><option value="">Auto-detect from description</option>{roles.map((role) => <option key={role.id} value={role.id}>{role.label}</option>)}</select></label><label>Location<input value={form.location} onChange={(event) => setForm({ ...form, location: event.target.value })} placeholder="Pune · hybrid" /></label></div>
        <div className="admin-form-row"><label>Company website <span>OPTIONAL</span><input type="url" value={form.website} onChange={(event) => setForm({ ...form, website: event.target.value })} placeholder="https://company.com" /></label><label>Industry <span>OPTIONAL</span><input value={form.industry} onChange={(event) => setForm({ ...form, industry: event.target.value })} placeholder="Semiconductors" /></label></div>
        <div className="admin-form-detail"><span className="admin-subhead"><Info size={15} /> About the company<small>What the company does</small></span><input value={form.about} onChange={(event) => setForm({ ...form, about: event.target.value })} placeholder="A short paragraph about the company and its work" /></div>
        <div className="admin-form-detail"><span className="admin-subhead"><GraduationCap size={15} /> Eligibility<small>Degree, year, CGPA or experience</small></span><textarea rows={2} value={form.eligibility} onChange={(event) => setForm({ ...form, eligibility: event.target.value })} placeholder="Final year B.Tech (CS/IT), MCA — GPA above 6.0" /></div>
        <div className="admin-form-row"><label>Selection process <small>One step per line</small><textarea rows={3} value={form.selection_process} onChange={(event) => setForm({ ...form, selection_process: event.target.value })} placeholder="Aptitude test&#10;Programming round&#10;HR interview" /></label><label>Perks &amp; benefits <small>One per line</small><textarea rows={3} value={form.perks} onChange={(event) => setForm({ ...form, perks: event.target.value })} placeholder="Mentorship&#10;Learning budget&#10;Medical insurance" /></label></div>
        <label>Job description<textarea required minLength={30} rows={8} value={form.raw_text} onChange={(event) => setForm({ ...form, raw_text: event.target.value })} placeholder="Paste the responsibilities, requirements, and qualifications…" /></label>
        <div className="admin-form-footer"><span><ShieldCheck size={15} /> Text is processed into structured skills automatically.</span><button className="button button-primary" disabled={submitting}>{submitting ? <LoaderCircle className="spin" size={17} /> : <><Plus size={16} /> Queue job description</>}</button></div>
      </form>
    </section>
      <section className="admin-jobs-card"><div className="admin-list-heading"><div><h2>Job descriptions</h2><p>{stats?.job_descriptions ?? 0} in the matching pool</p></div><label className="status-filter"><select value={filter} onChange={(event) => setFilter(event.target.value)}><option value="">All statuses</option><option value="ready">Ready</option><option value="pending">Pending</option><option value="error">Error</option></select><ChevronDown size={14} /></label></div>
        {loading ? <div className="loading-row"><LoaderCircle className="spin" size={18} /> Loading jobs</div> : <div className="admin-job-list">{jobs.map((job) => <button className="admin-job-row" key={job.id} onClick={() => viewJob(job)}><span className="job-company-mark">{initials(job.company)}</span><div className="admin-job-main"><strong>{job.title || job.company}</strong><small>{job.company} · {roles.find((role) => role.id === job.role_family)?.label || job.role_family || 'Unclassified'}</small></div><span className={`status-pill status-${job.status === 'ready' ? 'done' : job.status === 'error' ? 'failed' : 'pending'}`}><i />{statusLabel(job.status)}</span><div className="admin-job-actions" onClick={(event) => event.stopPropagation()}>{job.status === 'error' && <button onClick={() => reprocess(job.id)} title="Reprocess" aria-label={`Reprocess ${job.company}`}><LoaderCircle size={15} /></button>}<button onClick={() => archive(job.id)} title="Archive or delete" aria-label={`Archive ${job.company}`}><X size={15} /></button></div></button>)}{!jobs.length && <div className="empty-inline">No job descriptions found for this filter.</div>}</div>}
        <div className="admin-system-note"><span className="api-dot" /><span>AI extraction {stats?.config?.llm_enabled ? 'enabled' : 'using structured fallback'} · {stats?.config?.github_token_set ? 'GitHub connected' : 'GitHub not configured'}</span></div>
      </section></div>
    {detail && <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setDetail(null); }}><section className="company-modal jd-modal" role="dialog" aria-modal="true" aria-label={`${detail.company} job description details`}><button className="modal-close icon-button" onClick={() => setDetail(null)} aria-label="Close details"><X size={18} /></button>{detailData ? <JdDetailView data={detailData} roles={roles} /> : <div className="detail-loading"><LoaderCircle className="spin" size={22} /><span>Loading details</span></div>}</section></div>}
  </>;
}

function JdDetailView({ data, roles }) {
  const structured = data.structured || {};
  const companyName = data.company_name || data.company;
  const website = data.website || data.company_details?.website;
  const rows = [
    ['Employment type', structured.employment_type, Banknote],
    ['Compensation', structured.compensation, Banknote],
    ['Work mode', structured.work_mode, Globe2],
    ['Duration', structured.duration, CalendarClock],
    ['Conversion', structured.conversion, CalendarClock],
    ['Eligibility', structured.eligibility, GraduationCap],
  ].filter(([, value]) => value);
  return <><div className="modal-company-heading"><span className="company-monogram">{initials(companyName)}</span><div><span className="detail-eyebrow">JOB DESCRIPTION · #{data.id ?? data.jd_id}</span><h2>{data.title || 'Untitled position'}</h2><p>{companyName}{structured.location ? ` · ${structured.location}` : ''}</p></div></div><div className="jd-badge-row"><span className={`status-pill status-${data.status === 'ready' ? 'done' : data.status === 'error' ? 'failed' : 'pending'}`}><i />{statusLabel(data.status)}</span>{data.role_family && <span className="jd-badge">{roles.find((role) => role.id === data.role_family)?.label || data.role_family}</span>}{data.industry && <span className="jd-badge">{data.industry}</span>}</div>
    {structured.about && <div className="jd-detail-section"><span className="jd-detail-head"><Info size={15} /> About the company</span><p>{structured.about}</p></div>}
    {rows.length > 0 && <div className="jd-detail-section jd-detail-grid-content">{rows.map(([label, value, Icon]) => <div className="jd-detail-item" key={label}><Icon size={14} /><strong>{label}</strong><span>{value}</span></div>)}</div>}
    {(structured.selection_process || []).length > 0 && <div className="jd-detail-section"><span className="jd-detail-head"><ListChecks size={15} /> Selection process</span><ol className="jd-steps">{(structured.selection_process || []).map((step, index) => <li key={`${step}-${index}`}>{step}</li>)}</ol></div>}
    {(structured.perks || []).length > 0 && <div className="jd-detail-section"><span className="jd-detail-head"><Gift size={15} /> Perks &amp; benefits</span><div className="topic-list">{structured.perks.map((perk) => <span key={perk}>{perk}</span>)}</div></div>}
    {(structured.must_have || []).length > 0 && <div className="jd-detail-section"><span className="jd-detail-head"><Code2 size={15} /> Core skills</span><div className="topic-list">{structured.must_have.slice(0, 12).map((skill) => <span key={skill}>{skill}</span>)}</div></div>}
    {(structured.nice_to_have || []).length > 0 && <div className="jd-detail-section"><span className="jd-detail-head"><Sparkles size={15} /> Nice to have</span><div className="topic-list">{structured.nice_to_have.slice(0, 8).map((skill) => <span key={skill}>{skill}</span>)}</div></div>}
    {website && <a className="button button-outline full-button company-website" href={website} target="_blank" rel="noreferrer">Visit company <ArrowUpRight size={16} /></a>}
    <details className="jd-raw-text"><summary>Full job description</summary><pre>{data.raw_text}</pre></details>
  </>;
}

function LoadingPage({ label }) {
  return <div className="loading-page"><LoaderCircle className="spin" size={23} /><span>{label}</span></div>;
}

export default App;