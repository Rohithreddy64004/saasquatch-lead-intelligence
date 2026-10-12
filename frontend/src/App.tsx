import { useEffect, useRef, useState } from "react";
import Papa from "papaparse";
import {
  Activity,
  ArrowDown,
  ArrowRight,
  Bookmark,
  Building2,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  CloudUpload,
  Download,
  FileSpreadsheet,
  Filter,
  LayoutDashboard,
  LoaderCircle,
  MapPin,
  Menu,
  Plus,
  Search,
  Settings,
  ShieldCheck,
  Sparkles,
  Target,
  X,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import "./App.css";
import "./outreach.css";
import "./status-indicator.css";

const API = import.meta.env.VITE_API_URL || "";
type Lead = {
  id: string;
  company_name: string;
  industry: string | null;
  location: string | null;
  estimated_revenue: number | null;
  employee_count: number | null;
  domain: string | null;
  contact_name: string | null;
  contact_title: string | null;
  contact_email: string | null;
  growth_signal: string | null;
  growth_signal_source: string | null;
  source: string;
  is_synthetic: boolean;
  saved: boolean;
  score: number;
  priority: "High" | "Medium" | "Low";
  score_breakdown: Record<string, number>;
  reasons: string[];
  missing_information: string[];
  recommended_next_action: string;
  data_completeness: number;
  created_at: string;
};
type Filters = {
  search: string;
  industry: string;
  location: string;
  revenue_min: string;
  revenue_max: string;
  priority: string;
  min_score: string;
  sort_by: string;
  sort_dir: string;
};
type Page = "Overview" | "Leads" | "Saved Leads" | "Import Data" | "Settings";
type Dashboard = {
  total_leads: number;
  high_priority_leads: number;
  average_score: number;
  complete_contact_percentage: number;
  distribution: { priority: string; count: number }[];
  recent_leads: Lead[];
  top_leads: Lead[];
  industries: string[];
  locations: string[];
  score_weights: Record<string, number>;
};
type Outreach = {
  subject: string;
  email_body: string;
  linkedin_note: string;
  personalization_points: string[];
  data_limitations: string[];
  generated_by: "groq" | "template_generated";
  limited_information: boolean;
};
const emptyFilters: Filters = {
  search: "",
  industry: "",
  location: "",
  revenue_min: "",
  revenue_max: "",
  priority: "",
  min_score: "",
  sort_by: "created_at",
  sort_dir: "desc",
};
const categoryLabels: Record<string, string> = {
  company_fit: "Company & industry fit",
  revenue_fit: "Revenue fit",
  decision_maker: "Decision-maker relevance",
  growth_signals: "Growth signals",
  data_completeness: "Data completeness",
};
const money = (n: number | null) =>
  n == null
    ? "—"
    : new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "USD",
        notation: n >= 1_000_000 ? "compact" : "standard",
        maximumFractionDigits: n >= 1_000_000 ? 1 : 0,
      }).format(n);

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, init);
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      message = (await response.json()).detail || message;
    } catch {}
    throw Error(message);
  }
  return response.json() as Promise<T>;
}
function paramsFor(filters: Filters, extra: Record<string, string> = {}) {
  const params = new URLSearchParams();
  Object.entries({ ...filters, ...extra }).forEach(([key, value]) => {
    if (value) params.set(key, value);
  });
  return params.toString();
}

export default function App() {
  const [page, setPage] = useState<Page>("Overview"),
    [dashboard, setDashboard] = useState<Dashboard | null>(null),
    [leads, setLeads] = useState<Lead[]>([]),
    [total, setTotal] = useState(0),
    [pageNumber, setPageNumber] = useState(1),
    [filters, setFilters] = useState(emptyFilters),
    [selected, setSelected] = useState<Lead | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [mobileNav, setMobileNav] = useState(false),
    [selectedIds, setSelectedIds] = useState<string[]>([]),
    [csvFile, setCsvFile] = useState<File | null>(null),
    [preview, setPreview] = useState<string[][]>([]),
    [importReport, setImportReport] = useState<{
      accepted: number;
      rejected: number;
      duplicates: number;
      errors: string[];
    } | null>(null),
    [draft, setDraft] = useState<Outreach | null>(null),
    [draftBusy, setDraftBusy] = useState(false),
    [online, setOnline] = useState(false);
  const selectedLeadIdRef = useRef<string | null>(null);
  const draftRequestIdRef = useRef(0);
  const refreshDashboard = async () => {
    try {
      setDashboard(await api<Dashboard>("/api/dashboard"));
      setOnline(true);
      setError("");
    } catch (e) {
      setOnline(false);
      setError(e instanceof Error ? e.message : "Unable to reach API");
    }
  };
  const refreshLeads = async (p = pageNumber, f = filters) => {
    setBusy(true);
    try {
      const r = await api<{ items: Lead[]; total: number }>(
        `/api/leads?${paramsFor(f, { page: String(p), page_size: "10" })}`,
      );
      setLeads(r.items);
      setTotal(r.total);
      setSelectedIds([]);
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to load leads");
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => {
    void refreshDashboard();
  }, []);
  useEffect(() => {
    if (page === "Leads" || page === "Saved Leads")
      void refreshLeads(pageNumber, {
        ...filters,
        ...(page === "Saved Leads" ? { saved_only: "true" } : {}),
      } as Filters);
  }, [page, pageNumber, filters]);
  useEffect(() => {
    if (notice) {
      const timer = setTimeout(() => setNotice(""), 3500);
      return () => clearTimeout(timer);
    }
  }, [notice]);
  const navigate = (next: Page) => {
    setPage(next);
    setMobileNav(false);
    setPageNumber(1);
    setError("");
  };
  const setFilter = (key: keyof Filters, value: string) => {
    setFilters((current) => ({ ...current, [key]: value }));
    setPageNumber(1);
  };
  const chooseLead = (lead: Lead) => {
    selectedLeadIdRef.current = lead.id;
    draftRequestIdRef.current += 1;
    setSelected(lead);
    setDraft(null);
    setDraftBusy(false);
    setError("");
  };
  const closeLead = () => {
    selectedLeadIdRef.current = null;
    draftRequestIdRef.current += 1;
    setSelected(null);
    setDraft(null);
    setDraftBusy(false);
  };
  const toggleSaved = async (lead: Lead) => {
    try {
      const updated = await api<Lead>(`/api/leads/${lead.id}/save`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ saved: !lead.saved }),
      });
      setSelected(updated);
      setLeads((items) =>
        items.map((item) => (item.id === updated.id ? updated : item)),
      );
      await refreshDashboard();
      setNotice(updated.saved ? "Lead saved" : "Lead removed from saved");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to update lead");
    }
  };
  const exportCsv = async (ids?: string[]) => {
    try {
      const query = new URLSearchParams(
        paramsFor(filters, {
          ...(page === "Saved Leads" ? { saved_only: "true" } : {}),
          ...(ids?.length ? { selected_ids: ids.join(",") } : {}),
        }),
      );
      const response = await fetch(`${API}/api/leads/export?${query}`);
      if (!response.ok) throw Error("CSV export failed");
      const url = URL.createObjectURL(await response.blob()),
        a = document.createElement("a");
      a.href = url;
      a.download = "leads-export.csv";
      a.click();
      URL.revokeObjectURL(url);
      setNotice(`Exported ${ids?.length || total} leads`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Export failed");
    }
  };
  const chooseFile = (file: File | null) => {
    setCsvFile(file);
    setImportReport(null);
    setError("");
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".csv")) {
      setError("Choose a CSV file.");
      setCsvFile(null);
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const result = Papa.parse<string[]>(String(reader.result || ""), {
        preview: 6,
        skipEmptyLines: true,
      });
      setPreview(result.data);
      if (result.errors.length)
        setError(`CSV preview: ${result.errors[0].message}`);
    };
    reader.readAsText(file);
  };
  const importFile = async () => {
    if (!csvFile) return;
    setBusy(true);
    try {
      const form = new FormData();
      form.append("file", csvFile);
      const report = await api<{
        accepted: number;
        rejected: number;
        duplicates: number;
        errors: string[];
      }>("/api/leads/import", { method: "POST", body: form });
      setImportReport(report);
      setNotice(`Imported ${report.accepted} records`);
      await refreshDashboard();
      await refreshLeads(1, filters);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Import failed");
    } finally {
      setBusy(false);
    }
  };
  const makeDraft = async () => {
    if (!selected || draftBusy) return;
    const lead = selected;
    const requestId = ++draftRequestIdRef.current;
    setDraft(null);
    setDraftBusy(true);
    setError("");
    try {
      const result = await api<Outreach>(`/api/leads/${lead.id}/outreach`, {
        method: "POST",
      });
      if (
        selectedLeadIdRef.current !== lead.id ||
        draftRequestIdRef.current !== requestId
      )
        return;
      setDraft(result);
      setNotice(
        `${result.generated_by === "groq" ? "Groq draft" : "Template fallback"} ready for ${lead.company_name}`,
      );
    } catch (e) {
      if (
        selectedLeadIdRef.current === lead.id &&
        draftRequestIdRef.current === requestId
      ) {
        setError(
          e instanceof Error
            ? `Could not generate a draft for ${lead.company_name}: ${e.message}`
            : `Could not generate a draft for ${lead.company_name}. Try again.`,
        );
      }
    } finally {
      if (draftRequestIdRef.current === requestId) setDraftBusy(false);
    }
  };
  const copyDraft = async () => {
    if (!draft) return;
    await navigator.clipboard.writeText(
      `Subject: ${draft.subject}\n\n${draft.email_body}`,
    );
    setNotice("Email draft copied");
  };
  const navItems: [Page, typeof LayoutDashboard][] = [
    ["Overview", LayoutDashboard],
    ["Leads", Building2],
    ["Saved Leads", Bookmark],
    ["Import Data", CloudUpload],
    ["Settings", Settings],
  ];
  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobileNav ? "sidebar-open" : ""}`}>
        <div className="brand">
          <span className="brand-mark">
            <Target size={19} />
          </span>
          <span className="brand-copy">
            <b>SaaSquatch</b>
            <small>LEAD INTELLIGENCE</small>
          </span>
          <button
            className="icon-button mobile-close"
            onClick={() => setMobileNav(false)}
            aria-label="Close menu"
          >
            <X size={17} />
          </button>
        </div>
        <div className="workspace-label">WORKSPACE</div>
        <nav>
          {navItems.map(([label, Icon]) => (
            <button
              key={label}
              className={`nav-item ${page === label ? "active" : ""}`}
              onClick={() => navigate(label)}
            >
              <Icon size={17} />
              <span>{label}</span>
              {label === "Leads" && (
                <small>{dashboard?.total_leads ?? "—"}</small>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="workspace-card">
            <Activity size={16} />
            <span>
              <b>Intelligence workspace</b>
              <small>Demo environment</small>
            </span>
          </div>
          <div className="profile">
            <div className="avatar">SC</div>
            <span>
              <b>Sourcing team</b>
              <small>Team workspace</small>
            </span>
          </div>
        </div>
      </aside>
      {mobileNav && (
        <button
          className="mobile-scrim"
          onClick={() => setMobileNav(false)}
          aria-label="Close menu"
        />
      )}
      <main className="main-area">
        <header className="topbar">
          <button
            className="icon-button menu-toggle"
            onClick={() => setMobileNav(true)}
            aria-label="Open menu"
          >
            <Menu size={18} />
          </button>
          <div className="breadcrumb">
            Workspace <span>/</span> <b>{page}</b>
          </div>
          <div className="topbar-actions">
            <span className={`connection ${online ? "" : "offline"}`}>
              <i />
              {online ? "API connected" : "API unavailable"}
            </span>
            <button
              className="button primary small"
              onClick={() => navigate("Import Data")}
            >
              <Plus size={15} /> Add leads
            </button>
          </div>
        </header>
        <div className="content">
          {error && (
            <div className="alert">
              <CircleHelp size={16} />
              <span>
                {error}
                {!online && (
                  <>
                    . Start the backend at <code>localhost:8000</code>.
                  </>
                )}
              </span>
              <button onClick={() => setError("")} aria-label="Dismiss">
                <X size={15} />
              </button>
            </div>
          )}
          {notice && (
            <div className="toast">
              <Check size={15} />
              {notice}
            </div>
          )}
          {page === "Overview" && (
            <>
              <div className="page-heading">
                <div>
                  <div className="eyebrow">
                    SOURCING WORKSPACE <i />
                  </div>
                  <h1>Good morning, team</h1>
                  <p>Here’s your sourcing pipeline at a glance.</p>
                </div>
                <button
                  className="button primary"
                  onClick={() => navigate("Leads")}
                >
                  Explore leads <ArrowRight size={15} />
                </button>
              </div>
              <div className="metric-grid">
                <Metric
                  icon={Building2}
                  label="Total leads"
                  value={dashboard?.total_leads ?? "—"}
                  note="Across your pipeline"
                  tone="blue"
                />
                <Metric
                  icon={Target}
                  label="High priority"
                  value={dashboard?.high_priority_leads ?? "—"}
                  note="Score of 80 or above"
                  tone="green"
                />
                <Metric
                  icon={Activity}
                  label="Average score"
                  value={dashboard?.average_score ?? "—"}
                  note="Out of 100 points"
                  tone="amber"
                />
                <Metric
                  icon={ShieldCheck}
                  label="Complete contacts"
                  value={
                    dashboard
                      ? `${dashboard.complete_contact_percentage}%`
                      : "—"
                  }
                  note="Name, title and email"
                  tone="violet"
                />
              </div>
              <div className="overview-grid">
                <section className="panel distribution">
                  <PanelTitle
                    title="Lead distribution"
                    sub="Priority mix across your current pipeline"
                  />
                  <div className="chart">
                    {dashboard?.total_leads ? (
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart
                          data={dashboard.distribution}
                          margin={{ top: 10, right: 10, left: -22, bottom: 0 }}
                        >
                          <CartesianGrid vertical={false} stroke="#edf0f3" />
                          <XAxis
                            dataKey="priority"
                            tickLine={false}
                            axisLine={false}
                            tick={{ fill: "#7c8794", fontSize: 11 }}
                          />
                          <YAxis
                            allowDecimals={false}
                            tickLine={false}
                            axisLine={false}
                            tick={{ fill: "#9aa3ad", fontSize: 10 }}
                          />
                          <Tooltip
                            contentStyle={{
                              border: "1px solid #e8ebef",
                              borderRadius: 6,
                              fontSize: 11,
                            }}
                          />
                          <Bar
                            dataKey="count"
                            fill="#4a78d1"
                            radius={[4, 4, 0, 0]}
                            barSize={44}
                          />
                        </BarChart>
                      </ResponsiveContainer>
                    ) : (
                      <Empty message="No lead data yet" />
                    )}
                  </div>
                  <div className="legend">
                    <span>
                      <i />
                      Priority distribution · live database values
                    </span>
                  </div>
                </section>
                <section className="panel highest">
                  <PanelTitle
                    title="Highest priority"
                    sub="Strongest fit, ranked by score"
                    action={
                      <button
                        className="text-link"
                        onClick={() => navigate("Leads")}
                      >
                        View all <ArrowRight size={13} />
                      </button>
                    }
                  />
                  <div className="priority-list">
                    {dashboard?.top_leads.slice(0, 4).map((lead, i) => (
                      <button
                        className="priority-row"
                        key={lead.id}
                        onClick={() => chooseLead(lead)}
                      >
                        <span className="rank">0{i + 1}</span>
                        <Mark name={lead.company_name} />
                        <span className="priority-company">
                          <b>{lead.company_name}</b>
                          <small>
                            {lead.industry || "Unknown industry"} ·{" "}
                            {lead.location || "Unknown location"}
                          </small>
                        </span>
                        <Score priority={lead.priority} score={lead.score} />
                      </button>
                    ))}
                  </div>
                </section>
              </div>
              <section className="panel recent">
                <PanelTitle
                  title="Recently added"
                  sub="The latest companies in your pipeline"
                  action={
                    <button
                      className="text-link"
                      onClick={() => navigate("Leads")}
                    >
                      All leads <ArrowRight size={13} />
                    </button>
                  }
                />
                {dashboard?.recent_leads.slice(0, 5).map((lead) => (
                  <button
                    className="recent-row"
                    key={lead.id}
                    onClick={() => chooseLead(lead)}
                  >
                    <Mark name={lead.company_name} />
                    <span className="recent-company">
                      <b>{lead.company_name}</b>
                      <small>
                        {lead.contact_name || "Contact not identified"}
                        {lead.contact_title ? ` · ${lead.contact_title}` : ""}
                      </small>
                    </span>
                    <span className="recent-industry">
                      {lead.industry || "—"}
                    </span>
                    <small className="recent-date">
                      {new Date(lead.created_at).toLocaleDateString("en-US", {
                        month: "short",
                        day: "numeric",
                      })}
                    </small>
                    <Score priority={lead.priority} score={lead.score} />
                    <ArrowRight size={14} className="row-arrow" />
                  </button>
                ))}
              </section>
              <DemoNote />
            </>
          )}
          {(page === "Leads" || page === "Saved Leads") && (
            <>
              <div className="page-heading leads-heading">
                <div>
                  <div className="eyebrow">PIPELINE</div>
                  <h1>
                    {page === "Saved Leads" ? "Saved leads" : "Company leads"}
                  </h1>
                  <p>
                    Prioritize your next conversation with transparent fit
                    signals.
                  </p>
                </div>
                <div className="heading-actions">
                  <button
                    className="button outline"
                    onClick={() =>
                      void exportCsv(
                        selectedIds.length ? selectedIds : undefined,
                      )
                    }
                  >
                    <Download size={15} />
                    {selectedIds.length
                      ? `Export selected (${selectedIds.length})`
                      : "Export CSV"}
                  </button>
                  <button
                    className="button primary"
                    onClick={() => navigate("Import Data")}
                  >
                    <Plus size={15} /> Add leads
                  </button>
                </div>
              </div>
              <div className="filter-toolbar">
                <label className="search-field">
                  <Search size={15} />
                  <input
                    placeholder="Search companies or contacts"
                    value={filters.search}
                    onChange={(e) => setFilter("search", e.target.value)}
                  />
                </label>
                <label className="select-field">
                  <Filter size={14} />
                  <select
                    value={filters.industry}
                    onChange={(e) => setFilter("industry", e.target.value)}
                  >
                    <option value="">All industries</option>
                    {dashboard?.industries.map((item) => (
                      <option key={item}>{item}</option>
                    ))}
                  </select>
                  <ChevronDown size={13} />
                </label>
                <label className="select-field location-select">
                  <MapPin size={14} />
                  <input
                    placeholder="Location"
                    value={filters.location}
                    onChange={(e) => setFilter("location", e.target.value)}
                  />
                </label>
                <label className="select-field">
                  <select
                    value={filters.priority}
                    onChange={(e) => setFilter("priority", e.target.value)}
                  >
                    <option value="">Any priority</option>
                    <option>High</option>
                    <option>Medium</option>
                    <option>Low</option>
                  </select>
                  <ChevronDown size={13} />
                </label>
                <button
                  className="icon-button clear-filter"
                  title="Clear filters"
                  onClick={() => setFilters(emptyFilters)}
                >
                  <ArrowDown size={15} />
                </button>
              </div>
              <div className="advanced-filters">
                <span>Revenue</span>
                <input
                  type="number"
                  min="0"
                  placeholder="Min $"
                  value={filters.revenue_min}
                  onChange={(e) => setFilter("revenue_min", e.target.value)}
                />
                <span>to</span>
                <input
                  type="number"
                  min="0"
                  placeholder="Max $"
                  value={filters.revenue_max}
                  onChange={(e) => setFilter("revenue_max", e.target.value)}
                />
                <i />
                <span>Min score</span>
                <input
                  className="score-filter"
                  type="number"
                  min="0"
                  max="100"
                  placeholder="0"
                  value={filters.min_score}
                  onChange={(e) => setFilter("min_score", e.target.value)}
                />
                <span className="result-count">{total} companies</span>
              </div>
              <section className="panel table-panel">
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th className="check">
                          <input
                            type="checkbox"
                            aria-label="Select page"
                            checked={
                              leads.length > 0 &&
                              selectedIds.length === leads.length
                            }
                            onChange={(e) =>
                              setSelectedIds(
                                e.target.checked ? leads.map((x) => x.id) : [],
                              )
                            }
                          />
                        </th>
                        <th>
                          <button
                            className="sort"
                            onClick={() => {
                              setFilter("sort_by", "company_name");
                              setFilter(
                                "sort_dir",
                                filters.sort_dir === "asc" ? "desc" : "asc",
                              );
                            }}
                          >
                            Company <ArrowDown size={11} />
                          </button>
                        </th>
                        <th>Industry</th>
                        <th>Location</th>
                        <th>Revenue</th>
                        <th>Contact</th>
                        <th>
                          <button
                            className="sort"
                            onClick={() => {
                              setFilter("sort_by", "score");
                              setFilter(
                                "sort_dir",
                                filters.sort_dir === "asc" ? "desc" : "asc",
                              );
                            }}
                          >
                            Score <ArrowDown size={11} />
                          </button>
                        </th>
                        <th>Quality</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {busy ? (
                        <tr>
                          <td colSpan={9} className="loading">
                            <LoaderCircle className="spin" size={18} /> Loading
                            lead records…
                          </td>
                        </tr>
                      ) : (
                        leads.map((lead) => (
                          <tr key={lead.id}>
                            <td className="check">
                              <input
                                type="checkbox"
                                aria-label={`Select ${lead.company_name}`}
                                checked={selectedIds.includes(lead.id)}
                                onChange={() =>
                                  setSelectedIds((ids) =>
                                    ids.includes(lead.id)
                                      ? ids.filter((id) => id !== lead.id)
                                      : [...ids, lead.id],
                                  )
                                }
                              />
                            </td>
                            <td>
                              <button
                                className="company-cell"
                                onClick={() => chooseLead(lead)}
                              >
                                <Mark name={lead.company_name} />
                                <span>
                                  <b>{lead.company_name}</b>
                                  <small>
                                    {lead.domain || "Domain not added"}
                                  </small>
                                </span>
                              </button>
                            </td>
                            <td>
                              <span className="industry-tag">
                                {lead.industry || "—"}
                              </span>
                            </td>
                            <td>{lead.location || "—"}</td>
                            <td>{money(lead.estimated_revenue)}</td>
                            <td>
                              <span className="contact">
                                <b>{lead.contact_name || "Unknown contact"}</b>
                                <small>
                                  {lead.contact_title || "Title missing"}
                                </small>
                              </span>
                            </td>
                            <td>
                              <span
                                className={`score-text ${lead.priority.toLowerCase()}`}
                              >
                                <b>{lead.score}</b>
                                <small>{lead.priority}</small>
                              </span>
                            </td>
                            <td>
                              <span className="quality">
                                <i>
                                  <b
                                    style={{
                                      width: `${Math.max(lead.data_completeness, 4)}%`,
                                    }}
                                  />
                                </i>
                                <small>{lead.data_completeness}%</small>
                              </span>
                            </td>
                            <td>
                              <button
                                className={`icon-button save-mini ${lead.saved ? "saved" : ""}`}
                                onClick={() => void toggleSaved(lead)}
                                aria-label={
                                  lead.saved ? "Unsave lead" : "Save lead"
                                }
                              >
                                <Bookmark
                                  size={15}
                                  fill={lead.saved ? "currentColor" : "none"}
                                />
                              </button>
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                  {!busy && !leads.length && (
                    <div className="empty-table">
                      <Search size={21} />
                      <b>No companies match these filters</b>
                      <span>
                        Try a different search or broaden your filters.
                      </span>
                      <button
                        className="text-link"
                        onClick={() => setFilters(emptyFilters)}
                      >
                        Clear filters <ArrowRight size={13} />
                      </button>
                    </div>
                  )}
                </div>
                <div className="table-footer">
                  <span>
                    Showing{" "}
                    <b>
                      {total ? (pageNumber - 1) * 10 + 1 : 0}–
                      {Math.min(pageNumber * 10, total)}
                    </b>{" "}
                    of <b>{total}</b>
                  </span>
                  <div>
                    <button
                      className="icon-button"
                      disabled={pageNumber <= 1 || busy}
                      onClick={() => setPageNumber((n) => n - 1)}
                      aria-label="Previous page"
                    >
                      <ChevronLeft size={15} />
                    </button>
                    Page {pageNumber} of {Math.max(1, Math.ceil(total / 10))}
                    <button
                      className="icon-button"
                      disabled={pageNumber >= Math.ceil(total / 10) || busy}
                      onClick={() => setPageNumber((n) => n + 1)}
                      aria-label="Next page"
                    >
                      <ChevronRight size={15} />
                    </button>
                  </div>
                </div>
              </section>
              <DemoNote />
            </>
          )}
          {page === "Import Data" && (
            <>
              <div className="page-heading">
                <div>
                  <div className="eyebrow">DATA WORKSPACE</div>
                  <h1>Import companies</h1>
                  <p>
                    Bring your sourcing list into one clear, prioritized
                    pipeline.
                  </p>
                </div>
                <button
                  className="button outline"
                  onClick={() => void exportCsv()}
                >
                  <Download size={15} /> Export leads
                </button>
              </div>
              <div className="import-grid">
                <section className="panel import-panel">
                  <div className="section-heading">
                    <span>01</span>
                    <div>
                      <b>Upload a CSV file</b>
                      <small>
                        CSV only · up to 5 MB · Existing records are never
                        overwritten
                      </small>
                    </div>
                  </div>
                  <label className={`dropzone ${csvFile ? "has-file" : ""}`}>
                    <input
                      type="file"
                      accept=".csv,text/csv"
                      onChange={(e) => chooseFile(e.target.files?.[0] || null)}
                    />
                    {csvFile ? (
                      <>
                        <FileSpreadsheet size={24} />
                        <b>{csvFile.name}</b>
                        <small>
                          {(csvFile.size / 1024).toFixed(1)} KB · Select to
                          replace
                        </small>
                      </>
                    ) : (
                      <>
                        <CloudUpload size={25} />
                        <b>
                          Drop your file here, or <em>browse</em>
                        </b>
                        <small>CSV files up to 5 MB</small>
                      </>
                    )}
                  </label>
                  {preview.length > 0 && (
                    <>
                      <div className="preview-heading">
                        <b>Preview</b>
                        <span>
                          {Math.max(preview.length - 1, 0)} sample rows
                        </span>
                      </div>
                      <div className="preview-table">
                        <table>
                          <thead>
                            <tr>
                              {preview[0]?.map((x, i) => (
                                <th key={i}>{x || "Unnamed"}</th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {preview.slice(1).map((row, r) => (
                              <tr key={r}>
                                {preview[0]?.map((_, c) => (
                                  <td key={c}>{row[c] || "—"}</td>
                                ))}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                      <p className="mapped-note">
                        <Check size={14} /> Company name is required. Other
                        columns are matched by supported header names.
                      </p>
                      <button
                        className="button primary"
                        disabled={busy}
                        onClick={() => void importFile()}
                      >
                        {busy ? (
                          <LoaderCircle className="spin" size={15} />
                        ) : (
                          <CloudUpload size={15} />
                        )}{" "}
                        Import records
                      </button>
                    </>
                  )}
                  {importReport && (
                    <div className="report">
                      <b>Import complete</b>
                      <div>
                        <span>
                          <strong>{importReport.accepted}</strong> accepted
                        </span>
                        <span>
                          <strong>{importReport.duplicates}</strong> duplicates
                          skipped
                        </span>
                        <span>
                          <strong>{importReport.rejected}</strong> rejected
                        </span>
                      </div>
                      {importReport.errors.slice(0, 4).map((err, i) => (
                        <small key={i}>{err}</small>
                      ))}
                    </div>
                  )}
                </section>
                <aside className="panel import-aside">
                  <FileSpreadsheet size={20} />
                  <h3>Column guide</h3>
                  <p>Company name is required. Other columns are optional.</p>
                  <div className="column-list">
                    {[
                      ["Company", "company_name, company, name"],
                      ["Industry", "industry, sector"],
                      ["Location", "location, city"],
                      ["Revenue", "revenue, estimated_revenue"],
                      ["Employees", "employees, headcount"],
                      ["Domain", "domain, website"],
                      ["Contact", "contact_name, full name"],
                      ["Email", "email, contact_email"],
                    ].map(([key, value]) => (
                      <div key={key}>
                        <span>{key}</span>
                        <code>{value}</code>
                      </div>
                    ))}
                  </div>
                  <div className="dedupe-note">
                    <ShieldCheck size={15} />
                    <span>
                      Deduplicated by normalized domain, or company name and
                      location if no domain is present. Existing records are not
                      overwritten.
                    </span>
                  </div>
                  <a
                    download="lead-import-template.csv"
                    href={`data:text/csv;charset=utf-8,${encodeURIComponent("company_name,industry,location,estimated_revenue,employee_count,domain,contact_name,contact_title,contact_email\nExample Studio,SaaS,Denver CO,3500000,35,example-studio.example,Alex Morgan,Founder,alex@example.invalid")}`}
                  >
                    <Download size={14} /> Download CSV template
                  </a>
                </aside>
              </div>
              <DemoNote />
            </>
          )}
          {page === "Settings" && (
            <>
              <div className="page-heading">
                <div>
                  <div className="eyebrow">WORKSPACE</div>
                  <h1>Scoring settings</h1>
                  <p>
                    Understand the criteria behind each lead recommendation.
                  </p>
                </div>
                <span className="read-only-chip">
                  <ShieldCheck size={14} /> Transparent by design
                </span>
              </div>
              <div className="settings-grid">
                <section className="panel settings-panel">
                  <PanelTitle
                    title="Score composition"
                    sub="Five weighted categories, totaling 100 points"
                  />
                  {Object.entries(dashboard?.score_weights || {}).map(
                    ([key, weight]) => (
                      <div className="weight-row" key={key}>
                        <div>
                          <b>{categoryLabels[key] || key}</b>
                          <small>
                            {key === "company_fit"
                              ? "Exact targets score highest; adjacent sectors receive partial credit."
                              : key === "revenue_fit"
                                ? "Configured range scores highest; near-range values receive partial credit."
                                : key === "decision_maker"
                                  ? "Founder and executive roles score highest."
                                  : key === "growth_signals"
                                    ? "Only evidence with an explicit source is scored. Unknown signals receive zero."
                                    : "Nine company and contact fields contribute proportionally."}
                          </small>
                        </div>
                        <strong>
                          {weight}
                          <small> pts</small>
                        </strong>
                        <i>
                          <b style={{ width: `${weight * 4}%` }} />
                        </i>
                      </div>
                    ),
                  )}
                </section>
                <section className="panel settings-panel">
                  <PanelTitle
                    title="Priority thresholds"
                    sub="Used to sort your next move"
                  />
                  {[
                    ["High", "80–100", "Act on strong-fit leads"],
                    ["Medium", "60–79", "Review missing evidence"],
                    ["Low", "0–59", "Enrich before prioritizing"],
                  ].map(([name, range, desc]) => (
                    <div className="threshold-row" key={name}>
                      <i className={name.toLowerCase()} />
                      <b>{name}</b>
                      <span>{range}</span>
                      <small>{desc}</small>
                    </div>
                  ))}
                  <div className="settings-callout">
                    <CircleHelp size={15} />
                    <span>
                      Target industries and revenue range are configured on the
                      API server. Missing information never earns positive score
                      points.
                    </span>
                  </div>
                </section>
              </div>
              <DemoNote />
            </>
          )}
        </div>
        <footer className="footer">
          <span>
            SaaSquatch Lead Intelligence <i /> Sourcing workspace
          </span>
          <span>
            <ShieldCheck size={12} /> Synthetic demo data
          </span>
        </footer>
      </main>
      {selected && (
        <>
          <button
            className="drawer-backdrop"
            onClick={closeLead}
            aria-label="Close lead detail"
          />
          <aside className="drawer">
            <div className="drawer-top">
              <span>
                LEAD PROFILE · #{String(selected.id).padStart(4, "0")}
              </span>
              <button
                className="icon-button"
                onClick={closeLead}
                aria-label="Close"
              >
                <X size={18} />
              </button>
            </div>
            <div className="drawer-company">
              <Mark name={selected.company_name} large />
              <div>
                <h2>{selected.company_name}</h2>
                <span>
                  {selected.industry || "Industry unavailable"} ·{" "}
                  {selected.location || "Location unavailable"}
                </span>
              </div>
              <button
                className={`icon-button ${selected.saved ? "saved" : ""}`}
                onClick={() => void toggleSaved(selected)}
                aria-label="Save lead"
              >
                <Bookmark
                  size={17}
                  fill={selected.saved ? "currentColor" : "none"}
                />
              </button>
            </div>
            <div className="drawer-score">
              <strong>
                {selected.score}
                <small> / 100</small>
              </strong>
              <span
                className={`priority-tag ${selected.priority.toLowerCase()}`}
              >
                {selected.priority} priority
              </span>
              <span>Explainable fit score</span>
            </div>
            <section className="drawer-section">
              <PanelTitle title="Score breakdown" sub="WEIGHTED SIGNALS" />
              {Object.entries(selected.score_breakdown).map(([key, points]) => (
                <div className="breakdown-row" key={key}>
                  <span>{categoryLabels[key] || key}</span>
                  <i>
                    <b
                      style={{
                        width: `${Math.min((points / (dashboard?.score_weights[key] || 1)) * 100, 100)}%`,
                      }}
                    />
                  </i>
                  <strong>
                    {points}
                    <small>/{dashboard?.score_weights[key]}</small>
                  </strong>
                </div>
              ))}
              <div className="reason-list">
                {selected.reasons.map((reason, i) => (
                  <div key={i}>
                    <Check size={13} />
                    {reason}
                  </div>
                ))}
              </div>
            </section>
            <section className="drawer-section company-details">
              <PanelTitle title="Company details" sub="AVAILABLE RECORD" />
              <Detail
                label="Estimated revenue"
                value={money(selected.estimated_revenue)}
              />
              <Detail
                label="Employee count"
                value={
                  selected.employee_count?.toLocaleString() || "Not provided"
                }
              />
              <Detail
                label="Company domain"
                value={selected.domain || "Not provided"}
              />
              <Detail
                label="Contact"
                value={selected.contact_name || "Not identified"}
              />
              <Detail
                label="Role"
                value={selected.contact_title || "Not provided"}
              />
              <Detail
                label="Business email"
                value={selected.contact_email || "Not provided"}
              />
              {selected.growth_signal && (
                <Detail
                  label="Growth evidence"
                  value={`${selected.growth_signal} (${selected.growth_signal_source || "Source not stated"})`}
                />
              )}
            </section>
            <section className="data-warning">
              <b>
                <ShieldCheck size={14} /> Data quality ·{" "}
                {selected.data_completeness}% complete
              </b>
              {selected.missing_information.length ? (
                <ul>
                  {selected.missing_information.map((field) => (
                    <li key={field}>{field}</li>
                  ))}
                </ul>
              ) : (
                <p>No core fields are missing.</p>
              )}
              <p>{selected.recommended_next_action}</p>
            </section>
            <section className="drawer-section outreach">
              <PanelTitle title="Personalized outreach" sub="GROUNDED DRAFT" />
              {!draft ? (
                <div className="draft-prompt">
                  <p>
                    Generate a first touch grounded in {selected.company_name}'s
                    recorded details.
                  </p>
                  <button
                    className="button primary"
                    disabled={draftBusy}
                    onClick={() => void makeDraft()}
                  >
                    {draftBusy ? (
                      <LoaderCircle className="spin" size={14} />
                    ) : (
                      <Sparkles size={14} />
                    )}{" "}
                    {draftBusy ? "Generating draft..." : "Generate draft"}
                  </button>
                </div>
              ) : (
                <div className="draft-form">
                  <div className="draft-origin">
                    <Sparkles size={13} />
                    {draft.generated_by === "groq"
                      ? "Groq-assisted · grounded in this lead"
                      : "Company-grounded template fallback"}
                    {draft.limited_information && <small>Limited data</small>}
                  </div>
                  <div className="draft-personalization">
                    <b>PERSONALIZED FROM THIS RECORD</b>
                    {draft.personalization_points.length ? (
                      <ul>
                        {draft.personalization_points.map((point) => (
                          <li key={point}>{point}</li>
                        ))}
                      </ul>
                    ) : (
                      <p>Only the company name is available for personalization.</p>
                    )}
                  </div>
                  <label>
                    Subject
                    <input
                      value={draft.subject}
                      onChange={(e) =>
                        setDraft({ ...draft, subject: e.target.value })
                      }
                    />
                  </label>
                  <label>
                    Email
                    <textarea
                      rows={7}
                      value={draft.email_body}
                      onChange={(e) =>
                        setDraft({ ...draft, email_body: e.target.value })
                      }
                    />
                  </label>
                  <div className="linkedin">
                    <b>LINKEDIN NOTE</b>
                    <p>{draft.linkedin_note}</p>
                  </div>
                  {draft.data_limitations.length > 0 && (
                    <div className="draft-limitations">
                      <b>Data limitations</b>
                      <ul>
                        {draft.data_limitations.map((limitation) => (
                          <li key={limitation}>{limitation}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  <div className="draft-actions">
                    <button
                      className="button outline"
                      disabled={draftBusy}
                      onClick={() => void makeDraft()}
                    >
                      {draftBusy ? (
                        <LoaderCircle className="spin" size={14} />
                      ) : (
                        <Sparkles size={14} />
                      )}
                      {draftBusy ? "Regenerating..." : "Regenerate Draft"}
                    </button>
                    <button
                      className="button outline"
                      disabled={draftBusy}
                      onClick={() => void copyDraft()}
                    >
                      Copy email draft
                    </button>
                  </div>
                </div>
              )}
            </section>
            <p className="drawer-footnote">
              Generated text is a draft. Review for accuracy before sending.
            </p>
          </aside>
        </>
      )}
    </div>
  );
}

function Metric({
  icon: Icon,
  label,
  value,
  note,
  tone,
}: {
  icon: typeof Building2;
  label: string;
  value: string | number;
  note: string;
  tone: string;
}) {
  return (
    <div className="metric">
      <span className={`metric-icon ${tone}`}>
        <Icon size={16} />
      </span>
      <span className="metric-label">{label}</span>
      <b>{value}</b>
      <small>{note}</small>
    </div>
  );
}
function PanelTitle({
  title,
  sub,
  action,
}: {
  title: string;
  sub: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="panel-title">
      <div>
        <h2>{title}</h2>
        <p>{sub}</p>
      </div>
      {action}
    </div>
  );
}
function Mark({ name, large = false }: { name: string; large?: boolean }) {
  return (
    <span className={`mark ${large ? "large" : ""}`}>
      {name
        .split(/\s+/)
        .slice(0, 2)
        .map((part) => part[0])
        .join("")
        .toUpperCase()}
    </span>
  );
}
function Score({ priority, score }: { priority: string; score: number }) {
  return (
    <span className={`score-pill ${priority.toLowerCase()}`}>{score}</span>
  );
}
function DemoNote() {
  return (
    <div className="demo-note">
      <ShieldCheck size={14} /> Synthetic demonstration records. Example
      contacts and growth signals are fictional and not verified.
    </div>
  );
}
function Empty({ message }: { message: string }) {
  return (
    <div className="chart-empty">
      <Search size={18} />
      {message}
    </div>
  );
}
function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="detail-row">
      <span>{label}</span>
      <b>{value}</b>
    </div>
  );
}
