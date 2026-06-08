/* global React, ReactDOM, Icon, Kbd, LangCtx, Bi, Button, IconButton, Field, Input,
          PasswordInput, SearchInput, Textarea, Select, Toggle, Checkbox, Radio, RadioGroup,
          Status, Badge, Tag, Avatar, CodeChip, Banner, useToasts, ToastStack, Dialog, Drawer */
const { useState, useMemo } = React;

/* ──────────────────────────────────────────────────────────────────────────
   DATA — devices for the shell's centerpiece list
   ────────────────────────────────────────────────────────────────────────── */
const DEVICES = [
  { id: "vd-0042", name: "Marie's VaultDrive Pro", model: "VaultDrive Pro · 256 GB", owner: "Marie Tremblay",   ip: "100.94.12.4",   when: "2 min ago",   status: "secured", tags: ["laptop", "finance"], type: "VaultDrive Pro", os: "VaultOS 4.2.1", fp: "SHA256:7a3f9c2e84d1b6f0a52e1d9c8b7a4e3f1d6e91d" },
  { id: "bs-prod-1", name: "build-server prod-1",   model: "Linux · VaultCrypt 5.1", owner: "Jean-Luc Picard",  ip: "100.94.12.7",   when: "14 min ago",  status: "secured", tags: ["server", "ci"],     type: "VaultCrypt host", os: "Ubuntu 24.04 LTS", fp: "SHA256:9b2e7c4f8a1d3e6b9c5f2a7e4d1b8c3f6a9e2d5c" },
  { id: "lt-ahmed", name: "ahmed-laptop",           model: "macOS · VaultCrypt 5.0", owner: "Ahmed Hassan",    ip: "100.94.12.18",  when: "3 hr ago",    status: "update",  tags: ["laptop"],           type: "VaultCrypt host", os: "macOS 14.5", fp: "SHA256:4d8f1a7c2b5e9d3f6a8c1e4b7d2a5f8c3e6b9d2f" },
  { id: "hsm-net-01", name: "HSM-Network-01",       model: "VaultHSM Network",       owner: "Infrastructure",   ip: "100.94.12.99",  when: "Just now",    status: "secured", tags: ["production", "hsm", "fips-140-3"], type: "VaultHSM Network", os: "VaultOS 4.2.1", fp: "SHA256:c1d8e5b2a9f6c3d0e7b4a1f8c5d2b9e6a3f0d7c4" },
  { id: "vs-lobby", name: "VaultScan · lobby",      model: "VaultScan T-300",        owner: "Front desk",      ip: "100.94.12.31",  when: "1 hr ago",    status: "idle",    tags: ["biometric", "office-mtl"], type: "VaultScan", os: "VaultOS 3.8.7", fp: "SHA256:e6a1d4c7b0f3a6c9e2b5d8a1f4c7e0b3d6a9c2f5" },
  { id: "bkp-vault", name: "backup-vault",          model: "VaultBackup 4.2",        owner: "Backup service",   ip: "100.94.12.205", when: "6 hr ago",    status: "locked",  tags: ["backup"],           type: "VaultBackup service", os: "Ubuntu 22.04", fp: "SHA256:a2c5e8b1d4f7a0c3e6b9d2f5a8c1e4b7d0f3a6c9" },
  { id: "ip-marie",  name: "Marie's iPhone",        model: "iOS · VaultAccess 2.1", owner: "Marie Tremblay",   ip: "100.94.12.222", when: "4 days ago",  status: "offline", tags: ["mobile"],           type: "VaultAccess client", os: "iOS 18.2", fp: "SHA256:b3d0e7c4a1f8c5d2e9b6a3f0d7c4e1b8a5f2c9d6" },
];

const STATUS_COPY = {
  secured: <Bi en="Vault secured" fr="Coffre sécurisé" />,
  update:  <Bi en="Update available" fr="Mise à jour" />,
  idle:    <Bi en="Idle" fr="Inactif" />,
  locked:  <Bi en="Locked" fr="Verrouillé" />,
  offline: <Bi en="Offline" fr="Hors ligne" />,
};

/* ──────────────────────────────────────────────────────────────────────────
   APP SHELL pieces
   ────────────────────────────────────────────────────────────────────────── */

function TitleBar({ tab, setTab, lang, setLang, onCommand }) {
  return (
    <div className="titlebar">
      <div className="tb-left">
        <button className="workspace-pill" aria-label="Workspace">
          <span className="v-mark">V</span>
          <span className="ws-name">
            <span className="org">Acme Corp</span>
            <span className="env">production · ca-east</span>
          </span>
          <Icon name="chevron-down" size={13} className="chev" />
        </button>
      </div>
      <div className="tb-center">
        <div className="tabstrip">
          {[
            { id: "devices",  label: "Devices",  count: 34 },
            { id: "keys",     label: "Keys" },
            { id: "policies", label: "Policies" },
            { id: "audit",    label: "Audit log" },
            { id: "settings", label: "Settings" },
          ].map(t => (
            <button key={t.id} className={`tab ${tab === t.id ? "active" : ""}`} onClick={() => setTab(t.id)}>
              {t.label}
              {t.count != null && <span className="tab-count">{t.count}</span>}
            </button>
          ))}
        </div>
      </div>
      <div className="tb-right">
        <button className="tb-search" onClick={onCommand}>
          <Icon name="search" size={13} />
          <span>Search or jump to…</span>
          <span className="kbd"><Kbd>⌘K</Kbd></span>
        </button>
        <span className="tb-divider" />
        <div className="lang-toggle" role="group" aria-label="Language">
          <button className={lang === "en" ? "active" : ""} onClick={() => setLang("en")}>EN</button>
          <button className={lang === "fr" ? "active" : ""} onClick={() => setLang("fr")}>FR</button>
        </div>
        <button className="tb-icon-btn" aria-label="Help"><Icon name="help" size={14} /></button>
        <button className="tb-avatar" aria-label="Account">PP</button>
      </div>
    </div>
  );
}

function Sidebar() {
  const [active, setActive] = useState("devices");
  const items = [
    {
      head: <Bi en="Workspace" fr="Espace" />,
      rows: [
        { id: "overview", label: <Bi en="Overview" fr="Aperçu" />,   icon: "activity" },
        { id: "devices",  label: <Bi en="Devices" fr="Appareils" />, icon: "hard-drive", count: 34 },
        { id: "users",    label: <Bi en="Users" fr="Utilisateurs" />, icon: "users",     count: 12 },
      ],
    },
    {
      head: <Bi en="Security" fr="Sécurité" />,
      rows: [
        { id: "keys",    label: <Bi en="Keys & secrets" fr="Clés et secrets" />, icon: "key" },
        { id: "certs",   label: <Bi en="Certificates" fr="Certificats" />,       icon: "file-text" },
        { id: "audit",   label: <Bi en="Audit log" fr="Journal d'audit" />,      icon: "list" },
      ],
    },
    {
      head: <Bi en="Access" fr="Accès" />,
      rows: [
        { id: "policies", label: <Bi en="Policies" fr="Politiques" />,           icon: "shield" },
        { id: "tags",     label: <Bi en="Tags" fr="Étiquettes" />,               icon: "tag" },
        { id: "acl",      label: <Bi en="ACLs" fr="Listes de contrôle" />,       icon: "lock" },
      ],
    },
  ];
  return (
    <aside className="sidebar">
      {items.map((sec, i) => (
        <div key={i} className="sb-section">
          <div className="sb-section-head">{sec.head}</div>
          {sec.rows.map(r => (
            <button
              key={r.id}
              className={`sb-item ${active === r.id ? "active" : ""}`}
              onClick={() => setActive(r.id)}
            >
              <Icon name={r.icon} size={15} className="ico" />
              <span className="lab">{r.label}</span>
              {r.count != null && <span className="count">{r.count}</span>}
            </button>
          ))}
        </div>
      ))}
      <div className="sb-footer">
        <button className="sb-item">
          <Icon name="users-plus" size={15} className="ico" />
          <span className="lab"><Bi en="Invite people" fr="Inviter" /></span>
          <Kbd>I</Kbd>
        </button>
        <button className="sb-item">
          <Icon name="settings" size={15} className="ico" />
          <span className="lab"><Bi en="Settings" fr="Paramètres" /></span>
        </button>
      </div>
    </aside>
  );
}

function DevicesPage({ selected, setSelected, openInvite, openConfirm, pushToast }) {
  const [filter, setFilter] = useState("all");
  const [view, setView] = useState("list");
  const [checked, setChecked] = useState(new Set());
  const filtered = useMemo(() => {
    if (filter === "all") return DEVICES;
    if (filter === "secured") return DEVICES.filter(d => d.status === "secured");
    if (filter === "update")  return DEVICES.filter(d => d.status === "update");
    if (filter === "locked")  return DEVICES.filter(d => d.status === "locked");
    return DEVICES;
  }, [filter]);
  const toggleCheck = (id) => {
    setChecked(c => {
      const n = new Set(c); n.has(id) ? n.delete(id) : n.add(id); return n;
    });
  };

  return (
    <section className="main">
      <header className="page-head">
        <div className="page-head-top">
          <h1 className="page-title"><Bi en="Devices" fr="Appareils" /></h1>
          <span className="page-count">{filtered.length} / {DEVICES.length}</span>
          <div className="page-actions">
            <Button variant="ghost" size="sm" icon="filter"><Bi en="Filter" fr="Filtrer" /></Button>
            <Button variant="ghost" size="sm" icon="sliders"><Bi en="Sort" fr="Trier" /></Button>
            <Button variant="primary" size="sm" icon="plus" onClick={openInvite}><Bi en="Add device" fr="Ajouter" /></Button>
          </div>
        </div>
        <div className="row" style={{ justifyContent: "space-between" }}>
          <div className="segctl">
            {[
              { id: "all",     label: <Bi en="All" fr="Tous" />,           count: DEVICES.length },
              { id: "secured", label: <Bi en="Secured" fr="Sécurisés" />,  count: DEVICES.filter(d => d.status === "secured").length },
              { id: "update",  label: <Bi en="Updates" fr="Mises à jour"/>, count: DEVICES.filter(d => d.status === "update").length },
              { id: "locked",  label: <Bi en="Locked" fr="Verrouillés" />,  count: DEVICES.filter(d => d.status === "locked").length },
            ].map(s => (
              <button key={s.id} className={filter === s.id ? "active" : ""} onClick={() => setFilter(s.id)}>
                {s.label}<span className="count">{s.count}</span>
              </button>
            ))}
          </div>
          <div className="row">
            <div className="segctl" style={{ height: 26 }}>
              <button className={view === "list" ? "active" : ""} onClick={() => setView("list")} aria-label="List view"><Icon name="list" size={13} /></button>
              <button className={view === "grid" ? "active" : ""} onClick={() => setView("grid")} aria-label="Grid view"><Icon name="grid" size={13} /></button>
            </div>
          </div>
        </div>
      </header>

      <div className="datalist">
        <div className="dl-head">
          <div></div>
          <div><Bi en="Name" fr="Nom" /></div>
          <div><Bi en="Owner" fr="Propriétaire" /></div>
          <div><Bi en="Tailnet IP" fr="IP du réseau" /></div>
          <div><Bi en="Last seen" fr="Dernier accès" /></div>
          <div><Bi en="Status" fr="État" /></div>
          <div></div>
        </div>
        {filtered.map(d => (
          <div
            key={d.id}
            className={`dl-row ${selected === d.id ? "selected" : ""}`}
            onClick={() => setSelected(d.id)}
          >
            <button
              className={`check ${checked.has(d.id) ? "on" : ""}`}
              onClick={(e) => { e.stopPropagation(); toggleCheck(d.id); }}
              aria-label="Select"
            >
              {checked.has(d.id) && <Icon name="check" size={10} strokeWidth={3} />}
            </button>
            <div className="dl-cell-name">
              <Icon
                name={d.type.includes("HSM") ? "cpu" : d.type.includes("Scan") ? "scan" : d.type.includes("Backup") ? "server" : "hard-drive"}
                size={15}
                style={{ color: "var(--vault-slate)" }}
              />
              <div style={{ display: "flex", flexDirection: "column", lineHeight: 1.25, minWidth: 0 }}>
                <span className="nm">{d.name}</span>
                <span className="sub">{d.model}</span>
              </div>
            </div>
            <div className="dl-cell-owner">
              <Avatar name={d.owner} size={20} />
              <span style={{ fontSize: 13 }}>{d.owner}</span>
            </div>
            <div className="dl-cell-mono">{d.ip}</div>
            <div className="dl-cell-when">{d.when}</div>
            <div><Status tone={d.status} pulse={d.status === "secured" && d.when === "Just now"}>{STATUS_COPY[d.status]}</Status></div>
            <button className="dl-row-overflow" onClick={(e) => { e.stopPropagation(); pushToast({ tone: "info", title: "Row menu", description: "Overflow actions go here." }); }} aria-label="Actions">
              <Icon name="more" size={14} />
            </button>
          </div>
        ))}
      </div>
    </section>
  );
}

function DetailRail({ deviceId, onClose, openConfirm }) {
  const d = DEVICES.find(x => x.id === deviceId);
  const [tab, setTab] = useState("overview");
  if (!d) return null;
  return (
    <aside className="rail">
      <div className="rail-head">
        <div className="rail-head-top">
          <Icon
            name={d.type.includes("HSM") ? "cpu" : d.type.includes("Scan") ? "scan" : d.type.includes("Backup") ? "server" : "hard-drive"}
            size={16}
            style={{ color: "var(--vault-gold)" }}
          />
          <span className="ttl">{d.name}</span>
          <IconButton icon="x" label="Close detail" onClick={onClose} />
        </div>
        <div className="rail-head-meta">{d.id} · {d.os}</div>
        <div className="row" style={{ marginTop: 8, gap: 6, flexWrap: "wrap" }}>
          <Status tone={d.status}>{STATUS_COPY[d.status]}</Status>
          {d.tags.map(t => <Tag key={t}>{t}</Tag>)}
        </div>
      </div>
      <div className="rail-tabs">
        {[
          { id: "overview",    label: <Bi en="Overview"    fr="Aperçu" /> },
          { id: "permissions", label: <Bi en="Permissions" fr="Permissions" /> },
          { id: "activity",    label: <Bi en="Activity"    fr="Activité" /> },
        ].map(t => (
          <button key={t.id} className={tab === t.id ? "active" : ""} onClick={() => setTab(t.id)}>{t.label}</button>
        ))}
      </div>
      <div className="rail-body">
        {tab === "overview" && (
          <>
            <div className="rail-prop">
              <div className="pl"><Bi en="Type" fr="Type" /></div>
              <div className="pv">{d.type}</div>
            </div>
            <div className="rail-prop">
              <div className="pl"><Bi en="Owner" fr="Propriétaire" /></div>
              <div className="pv row"><Avatar name={d.owner} size={18} /> {d.owner}</div>
            </div>
            <div className="rail-prop">
              <div className="pl"><Bi en="Tailnet IP" fr="IP" /></div>
              <div className="pv mono">{d.ip}</div>
            </div>
            <div className="rail-prop">
              <div className="pl"><Bi en="Public key fingerprint" fr="Empreinte clé publique" /></div>
              <div className="pv mono">{d.fp}</div>
            </div>
            <div className="rail-prop">
              <div className="pl"><Bi en="Encryption" fr="Chiffrement" /></div>
              <div className="pv row" style={{ gap: 6 }}>
                <Badge tone="fips">AES-256-XTS</Badge>
                <Badge tone="outline">TLS 1.3</Badge>
              </div>
            </div>
            <div className="rail-prop">
              <div className="pl"><Bi en="Compliance" fr="Conformité" /></div>
              <div className="pv row" style={{ gap: 6, flexWrap: "wrap" }}>
                <Badge tone="fips">FIPS 140-3 L3</Badge>
                <Badge tone="outline">CC EAL4+</Badge>
              </div>
            </div>
          </>
        )}
        {tab === "permissions" && (
          <>
            <div className="rail-prop">
              <div className="pl"><Bi en="Access scope" fr="Portée d'accès" /></div>
              <div className="pv"><Bi en="Production network · 4 subnets" fr="Réseau production · 4 sous-réseaux" /></div>
            </div>
            <div style={{ borderTop: "1px solid var(--vault-divider)", paddingTop: 12 }} />
            <Toggle on={true}><Bi en="Auto-lock after 5 minutes idle" fr="Verrouillage auto. après 5 min" /></Toggle>
            <Toggle on={true}><Bi en="Require biometric on unlock" fr="Biométrie au déverrouillage" /></Toggle>
            <Toggle on={false}><Bi en="Allow USB pass-through" fr="USB de passage" /></Toggle>
            <Toggle on={true}><Bi en="Push security events to SIEM" fr="Envoyer les évén. au SIEM" /></Toggle>
          </>
        )}
        {tab === "activity" && (
          <>
            {[
              { t: <Bi en="Vault unlocked"           fr="Coffre déverrouillé" />,    s: "Just now",  by: d.owner, tone: "secured" },
              { t: <Bi en="Policy updated"           fr="Politique mise à jour" />,  s: "12 min ago", by: "Patrick Potvin", tone: "idle" },
              { t: <Bi en="Firmware verified"        fr="Micrologiciel vérifié" />,   s: "1 hr ago",   by: "system",  tone: "secured" },
              { t: <Bi en="Key rotated"              fr="Clé alternée" />,            s: "2 days ago", by: "system",  tone: "secured" },
            ].map((e, i) => (
              <div key={i} style={{ display: "flex", gap: 10, alignItems: "flex-start", paddingBottom: 10, borderBottom: "1px solid var(--vault-divider)" }}>
                <span className={`dot ${e.tone}`} style={{ marginTop: 5 }} />
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13 }}>{e.t}</div>
                  <div style={{ fontSize: 11.5, color: "var(--vault-muted)", marginTop: 2 }}>
                    {e.s} · <span className="mono">{e.by}</span>
                  </div>
                </div>
              </div>
            ))}
          </>
        )}
      </div>
      <div className="rail-foot">
        <Button variant="secondary" size="sm" icon="rotate"><Bi en="Rotate keys" fr="Alterner clés" /></Button>
        <Button variant="ghost" size="sm" icon="lock"><Bi en="Disable" fr="Désactiver" /></Button>
        <span className="stretch" />
        <Button variant="danger" size="sm" icon="trash" onClick={openConfirm}><Bi en="Remove" fr="Retirer" /></Button>
      </div>
    </aside>
  );
}

function StatusBar() {
  return (
    <div className="statusbar">
      <div className="sb-cluster">
        <span className="sb-item">
          <span className="dot secured" style={{ width: 6, height: 6, borderRadius: 999, background: "var(--vault-green)" }} />
          <span><Bi en="Connected" fr="Connecté" /> · prod-region-east</span>
        </span>
        <span className="sb-item"><Icon name="users" size={11} /> 12 <Bi en="online" fr="en ligne" /></span>
      </div>
      <div className="sb-cluster center">
        <span className="sb-item"><Icon name="lock" size={11} /> AES-256-XTS · TLS 1.3 · ML-KEM-1024</span>
      </div>
      <div className="sb-cluster right">
        <span className="sb-item"><Icon name="refresh" size={11} /> <Bi en="Synced 12s ago" fr="Sync il y a 12s" /></span>
        <span className="env-pill">prod</span>
      </div>
    </div>
  );
}

/* ──────────────────────────────────────────────────────────────────────────
   DESIGN LIBRARY SECTION — components in isolation
   ────────────────────────────────────────────────────────────────────────── */

function LibSection({ id, title, description, children }) {
  return (
    <section id={id} className="lib-section">
      <div className="lib-section-head">
        <h3>{title}</h3>
        <p>{description}</p>
      </div>
      <div className="lib-tile">{children}</div>
    </section>
  );
}

function LibButtons() {
  return (
    <LibSection id="buttons" title="Buttons"
      description="Tight 30px height by default. Primary is gold; icons inherit text color; keyboard hints live inside the button itself.">
      <div>
        <div className="lib-cap">Variants</div>
        <div className="row" style={{ marginTop: 8 }}>
          <Button variant="primary" icon="plus">Add device</Button>
          <Button variant="secondary">Continue</Button>
          <Button variant="ghost">Cancel</Button>
          <Button variant="danger" icon="trash">Remove</Button>
        </div>
      </div>
      <div>
        <div className="lib-cap">With keyboard hints</div>
        <div className="row" style={{ marginTop: 8 }}>
          <Button variant="secondary" icon="search" kbd="⌘K">Search</Button>
          <Button variant="secondary" kbd="⏎">Confirm</Button>
          <Button variant="ghost" kbd="Esc">Dismiss</Button>
        </div>
      </div>
      <div>
        <div className="lib-cap">Sizes</div>
        <div className="row" style={{ marginTop: 8 }}>
          <Button variant="secondary" size="sm">Small</Button>
          <Button variant="secondary">Default</Button>
          <Button variant="secondary" size="lg">Large</Button>
          <IconButton icon="settings" label="Settings" />
          <IconButton icon="refresh" label="Refresh" variant="secondary" />
        </div>
      </div>
      <div>
        <div className="lib-cap">States</div>
        <div className="row" style={{ marginTop: 8 }}>
          <Button variant="primary">Default</Button>
          <Button variant="primary" disabled>Disabled</Button>
          <Button variant="secondary" disabled>Disabled</Button>
        </div>
      </div>
    </LibSection>
  );
}

function LibInputs() {
  const [val, setVal] = useState("VWCR-9F4A-2C71-88E3-AB1D");
  return (
    <LibSection id="inputs" title="Inputs"
      description="32px controls, cyan focus halo (no glow), monospace mode for IDs and secrets. Errors get a soft burgundy ring.">
      <div className="lib-grid-2">
        <Field label={<Bi en="License key" fr="Clé de licence" />} num="01" hint="VaultWares portal → My licenses">
          <Input mono value={val} onChange={e => setVal(e.target.value)} />
        </Field>
        <Field label={<Bi en="Master password" fr="Mot de passe maître" />} num="02" hint="Cannot be recovered. Store somewhere safe.">
          <PasswordInput defaultValue="my-very-strong-passphrase-2026" />
        </Field>
        <Field label={<Bi en="Algorithm" fr="Algorithme" />} num="03">
          <Select options={[
            { value: "aes", label: "AES-256-XTS" },
            { value: "cha", label: "ChaCha20-Poly1305" },
          ]} />
        </Field>
        <Field label={<Bi en="Device path" fr="Chemin du périphérique" />} num="04" error={<Bi en="No device matched. Try /dev/sdc." fr="Aucun périphérique trouvé. Essayez /dev/sdc." />}>
          <Input mono defaultValue="/dev/sd?" error />
        </Field>
        <Field label={<Bi en="Search" fr="Recherche" />} num="05">
          <SearchInput placeholder="Search devices, keys, policies…" />
        </Field>
        <Field label={<Bi en="Notes" fr="Notes" />} num="06" hint="Optional. Free text, EN/FR.">
          <Textarea placeholder="…" defaultValue="" rows={3} />
        </Field>
      </div>
    </LibSection>
  );
}

function LibToggles() {
  const [a, setA] = useState(true);
  const [b, setB] = useState(true);
  const [c, setC] = useState(false);
  const [d, setD] = useState(false);
  const [scope, setScope] = useState("prod");
  return (
    <LibSection id="toggles" title="Toggles, checks, radios"
      description="Toggles use green for ON (signals 'live / secured'). Checks use gold (it's a brand action). Radios use cyan (it's interaction).">
      <div className="lib-grid-2">
        <div className="row-vstack">
          <div className="lib-cap">Toggle</div>
          <Toggle on={a} onChange={setA}><Bi en="Auto-lock after 5 minutes idle" fr="Verrouillage auto. après 5 min d'inactivité" /></Toggle>
          <Toggle on={b} onChange={setB}><Bi en="Require biometric on unlock" fr="Biométrie au déverrouillage" /></Toggle>
          <Toggle on={c} onChange={setC}><Bi en="Allow USB pass-through" fr="Autoriser l'USB de passage" /></Toggle>
        </div>
        <div className="row-vstack">
          <div className="lib-cap">Checkbox</div>
          <Checkbox on={true}><Bi en="I have a master password backup" fr="J'ai une sauvegarde du mot de passe" /></Checkbox>
          <Checkbox on={false}><Bi en="Send anonymous diagnostics" fr="Envoyer des diagnostics anonymes" /></Checkbox>
          <Checkbox on={true}><Bi en="Push security events to SIEM" fr="Envoyer les évén. au SIEM" /></Checkbox>
        </div>
        <div className="row-vstack">
          <div className="lib-cap">Radio group</div>
          <RadioGroup
            value={scope}
            onChange={setScope}
            options={[
              { value: "prod",  label: <Bi en="Production · 4 subnets"  fr="Production · 4 sous-réseaux" /> },
              { value: "stage", label: <Bi en="Staging · 2 subnets"      fr="Pré-prod · 2 sous-réseaux" /> },
              { value: "dev",   label: <Bi en="Development · local only" fr="Développement · local seulement" /> },
            ]}
          />
        </div>
        <div className="row-vstack">
          <div className="lib-cap">Disabled state</div>
          <Toggle on={false}><span style={{ opacity: 0.5 }}><Bi en="Requires Enterprise plan" fr="Plan Enterprise requis" /></span></Toggle>
          <Checkbox on={false}><span style={{ opacity: 0.5 }}>Disabled checkbox</span></Checkbox>
        </div>
      </div>
    </LibSection>
  );
}

function LibStatus() {
  return (
    <LibSection id="status" title="Status indicators"
      description="Telegraphic: a 6px colored dot + label, never a bubble pill. Pulse only for live states. Badges are mono and tight; tags are lower-density.">
      <div>
        <div className="lib-cap">Status dots</div>
        <div className="row" style={{ marginTop: 8, gap: 16 }}>
          <Status tone="secured" pulse><Bi en="Vault secured" fr="Coffre sécurisé" /></Status>
          <Status tone="update"><Bi en="Update available" fr="Mise à jour" /></Status>
          <Status tone="idle"><Bi en="Idle" fr="Inactif" /></Status>
          <Status tone="locked"><Bi en="Locked" fr="Verrouillé" /></Status>
          <Status tone="offline"><Bi en="Offline" fr="Hors ligne" /></Status>
        </div>
      </div>
      <div>
        <div className="lib-cap">Compliance badges</div>
        <div className="row" style={{ marginTop: 8, gap: 6, flexWrap: "wrap" }}>
          <Badge tone="fips">FIPS 140-3 · L3</Badge>
          <Badge tone="outline">CC EAL4+</Badge>
          <Badge tone="outline">GDPR</Badge>
          <Badge tone="outline">HIPAA</Badge>
          <Badge tone="outline">PCI DSS</Badge>
          <Badge tone="outline">SOC 2</Badge>
        </div>
      </div>
      <div>
        <div className="lib-cap">Edition tags</div>
        <div className="row" style={{ marginTop: 8, gap: 6 }}>
          <Badge>Standard</Badge>
          <Badge tone="warning">Professional</Badge>
          <Badge tone="gold">Enterprise</Badge>
        </div>
      </div>
      <div>
        <div className="lib-cap">Tags (removable)</div>
        <div className="row" style={{ marginTop: 8, gap: 6, flexWrap: "wrap" }}>
          <Tag>production</Tag>
          <Tag>hsm</Tag>
          <Tag onRemove={() => {}}>fips-140-3</Tag>
          <Tag onRemove={() => {}}>office-mtl</Tag>
        </div>
      </div>
      <div>
        <div className="lib-cap">Code chips (copy)</div>
        <div className="row" style={{ marginTop: 8, gap: 8, flexWrap: "wrap" }}>
          <CodeChip>100.94.12.99</CodeChip>
          <CodeChip>SHA256:c1d8e5b2a9f6c3d0e7b4a1f8c5d2b9e6a3f0d7c4</CodeChip>
          <CodeChip>/dev/sdc</CodeChip>
        </div>
      </div>
    </LibSection>
  );
}

function LibCards() {
  return (
    <LibSection id="cards" title="Cards"
      description="Instrument-style: hairline border, no shadow, optional mono strip on top with metadata. Product / status / metric variants.">
      <div className="lib-grid-3">
        <article className="card">
          <div className="card-strip">
            <Icon name="hard-drive" size={12} />
            <span>VAULT · /dev/sdc</span>
            <span style={{ marginLeft: "auto" }}>2m ago</span>
          </div>
          <h3><Bi en="Marie's VaultDrive Pro" fr="VaultDrive de Marie" /></h3>
          <p style={{ margin: "4px 0 12px", fontSize: 12.5, color: "var(--vault-muted)" }}>
            <Bi en="256 GB · biometric unlock · auto-lock 5m" fr="256 Go · biométrie · verr. 5 min" />
          </p>
          <div className="row" style={{ justifyContent: "space-between" }}>
            <Status tone="secured"><Bi en="Secured" fr="Sécurisé" /></Status>
            <Button variant="ghost" size="sm" trailingIcon="arrow-right"><Bi en="Manage" fr="Gérer" /></Button>
          </div>
        </article>
        <article className="card">
          <div className="card-strip">
            <Icon name="cpu" size={12} />
            <span>HSM-NET-01</span>
            <span style={{ marginLeft: "auto" }}>just now</span>
          </div>
          <h3>VaultHSM Network</h3>
          <p style={{ margin: "4px 0 12px", fontSize: 12.5, color: "var(--vault-muted)" }}>
            <Bi en="PCIe HSM · production cluster · 4 keys active" fr="HSM PCIe · cluster prod · 4 clés actives" />
          </p>
          <div className="row" style={{ gap: 6 }}>
            <Badge tone="fips">FIPS 140-3 L3</Badge>
            <Badge tone="outline">CC EAL4+</Badge>
          </div>
        </article>
        <article className="card">
          <div className="card-strip">
            <Icon name="activity" size={12} />
            <span>LAST 7 DAYS</span>
          </div>
          <h3 style={{ fontSize: 12, color: "var(--vault-muted)", fontWeight: 400, textTransform: "uppercase", letterSpacing: "0.06em" }}>
            <Bi en="Vault unlocks" fr="Déverrouillages" />
          </h3>
          <div className="metric-num" style={{ marginTop: 6 }}>1,284</div>
          <div className="row" style={{ marginTop: 4 }}>
            <span className="metric-delta">+12.4%</span>
            <span style={{ fontSize: 11, color: "var(--vault-muted)" }}>
              <Bi en="vs prior 7 days" fr="vs 7 jours préc." />
            </span>
          </div>
          {/* sparkline */}
          <svg viewBox="0 0 120 28" style={{ marginTop: 10, width: "100%", height: 28 }} preserveAspectRatio="none">
            <polyline points="0,20 10,18 20,22 30,16 40,18 50,12 60,14 70,10 80,8 90,12 100,6 110,8 120,4"
              fill="none" stroke="#CC9B21" strokeWidth="1.5" />
          </svg>
        </article>
      </div>
    </LibSection>
  );
}

function LibBanners({ pushToast }) {
  return (
    <LibSection id="banners" title="Banners & toasts"
      description="Banners have a 3px tone-colored left edge (square corners on the left). Toasts dock to the bottom-right with a 240ms entry, no infinite animation.">
      <div className="row-vstack">
        <Banner tone="success" title={<Bi en="Vault secured." fr="Coffre sécurisé." />}>
          <Bi
            en="All volumes encrypted with AES-256-XTS. Key fingerprint verified against the registry."
            fr="Tous les volumes sont chiffrés en AES-256-XTS. Empreinte vérifiée auprès du registre."
          />
        </Banner>
        <Banner tone="warning" title={<Bi en="Attention required" fr="Attention requise" />}
          actions={<Button size="sm" variant="secondary"><Bi en="Update now" fr="Mettre à jour" /></Button>}>
          <Bi
            en="Firmware update available for 3 VaultDrive devices."
            fr="Mise à jour disponible pour 3 VaultDrive."
          />
        </Banner>
        <Banner tone="danger" title={<Bi en="We noticed something." fr="Nous avons remarqué quelque chose." />}>
          <Bi
            en="Auto-lock policy is not enforced on 2 devices. Here's what to do."
            fr="La politique de verrouillage auto. n'est pas appliquée sur 2 appareils. Voici la marche à suivre."
          />
        </Banner>
        <Banner tone="info" title={<Bi en="Heads up" fr="Information" />}>
          <Bi
            en="Offline activation requires the portal. No internet connection is sent."
            fr="L'activation hors ligne passe par le portail. Aucune connexion Internet n'est utilisée."
          />
        </Banner>
      </div>
      <div className="row">
        <Button variant="secondary" size="sm" icon="bell" onClick={() => pushToast({ tone: "success", title: "Vault secured.", description: "marie's-vaultdrive · 256 GB" })}>Toast · success</Button>
        <Button variant="secondary" size="sm" icon="bell" onClick={() => pushToast({ tone: "warning", title: "Update available", description: "3 VaultDrives can update to 5.1.2" })}>Toast · warning</Button>
        <Button variant="secondary" size="sm" icon="bell" onClick={() => pushToast({ tone: "danger",  title: "Auto-lock disabled", description: "2 devices · review policy" })}>Toast · danger</Button>
      </div>
    </LibSection>
  );
}

function LibForm({ pushToast }) {
  const [step, setStep] = useState(1);
  const [name, setName] = useState("");
  const [algo, setAlgo] = useState("aes");
  const [agree, setAgree] = useState(false);
  const nameError = step === 2 && !name.trim() ? <Bi en="Required field." fr="Champ obligatoire." /> : null;
  return (
    <LibSection id="form" title="Form · multi-step"
      description="Three steps with numbered legal-form labels, inline validation, and a footer that pins primary actions to the right.">
      <div className="row" style={{ gap: 4 }}>
        {[1, 2, 3].map(s => (
          <div key={s} className="row" style={{ gap: 8 }}>
            <span style={{
              width: 22, height: 22, borderRadius: 999,
              display: "inline-flex", alignItems: "center", justifyContent: "center",
              fontSize: 11, fontWeight: 600,
              background: step >= s ? "var(--vault-gold)" : "rgba(0,43,54,0.06)",
              color: step >= s ? "var(--vault-paper)" : "var(--vault-muted)",
              fontFamily: "var(--vault-font-mono)",
            }}>{s}</span>
            <span style={{ fontSize: 13, color: step >= s ? "var(--vault-ink)" : "var(--vault-muted)", marginRight: 6 }}>
              {[<Bi en="Identify" fr="Identifier" />, <Bi en="Encrypt" fr="Chiffrer" />, <Bi en="Confirm" fr="Confirmer" />][s - 1]}
            </span>
            {s < 3 && <span style={{ width: 24, height: 1, background: "var(--vault-border-subtle)" }} />}
          </div>
        ))}
      </div>
      <div className="lib-divider" />
      {step === 1 && (
        <div className="lib-grid-2">
          <Field label={<Bi en="Device name" fr="Nom de l'appareil" />} num="01" hint={<Bi en="A descriptive name. Sentence case." fr="Un nom descriptif." />} error={nameError}>
            <Input value={name} onChange={e => setName(e.target.value)} placeholder="Marie's VaultDrive Pro" error={!!nameError} />
          </Field>
          <Field label={<Bi en="Owner" fr="Propriétaire" />} num="02">
            <Select options={[{ value: "marie", label: "Marie Tremblay" }, { value: "jean", label: "Jean-Luc Picard" }]} />
          </Field>
        </div>
      )}
      {step === 2 && (
        <div className="lib-grid-2">
          <Field label={<Bi en="Algorithm" fr="Algorithme" />} num="03">
            <RadioGroup
              value={algo}
              onChange={setAlgo}
              options={[
                { value: "aes", label: <span><span className="mono">AES-256-XTS</span> · <Bi en="recommended" fr="recommandé" /></span> },
                { value: "cha", label: <span className="mono">ChaCha20-Poly1305</span> },
              ]}
            />
          </Field>
          <Field label={<Bi en="Key source" fr="Source de clé" />} num="04">
            <RadioGroup
              value="pw"
              onChange={() => {}}
              options={[
                { value: "pw",  label: <Bi en="Master password" fr="Mot de passe maître" /> },
                { value: "hsm", label: <Bi en="HSM-backed key"  fr="Clé adossée HSM" /> },
                { value: "fp",  label: <span><Bi en="Fingerprint enrollment" fr="Inscription d'empreinte" /> <span className="mono" style={{ color: "var(--vault-muted)" }}>·biometric</span></span> },
              ]}
            />
          </Field>
        </div>
      )}
      {step === 3 && (
        <div className="row-vstack">
          <div className="row" style={{ gap: 10, fontSize: 13 }}>
            <span className="muted"><Bi en="Device" fr="Appareil" /></span>
            <span>{name || "—"}</span>
          </div>
          <div className="row" style={{ gap: 10, fontSize: 13 }}>
            <span className="muted"><Bi en="Algorithm" fr="Algorithme" /></span>
            <CodeChip>{algo === "aes" ? "AES-256-XTS" : "ChaCha20-Poly1305"}</CodeChip>
          </div>
          <Checkbox on={agree} onChange={setAgree}>
            <Bi
              en="I have a backup of the master password. VaultWares cannot recover it."
              fr="J'ai une sauvegarde du mot de passe maître. VaultWares ne peut pas le récupérer."
            />
          </Checkbox>
        </div>
      )}
      <div className="lib-divider" />
      <div className="row" style={{ justifyContent: "space-between" }}>
        <Button variant="ghost" disabled={step === 1} onClick={() => setStep(s => s - 1)} icon="arrow-left"><Bi en="Back" fr="Retour" /></Button>
        <div className="row" style={{ gap: 6 }}>
          <Button variant="ghost"><Bi en="Cancel" fr="Annuler" /></Button>
          {step < 3 ? (
            <Button variant="primary" trailingIcon="arrow-right" onClick={() => {
              if (step === 1 && !name.trim()) { setStep(2); return; } // surface error
              setStep(s => Math.min(3, s + 1));
            }}><Bi en="Continue" fr="Continuer" /></Button>
          ) : (
            <Button variant="primary" icon="shield-check" disabled={!agree} onClick={() => {
              pushToast({ tone: "success", title: "Vault secured.", description: name || "Untitled" });
              setStep(1); setName(""); setAgree(false);
            }}><Bi en="Encrypt and finish" fr="Chiffrer et terminer" /></Button>
          )}
        </div>
      </div>
    </LibSection>
  );
}

function LibBilingual() {
  return (
    <LibSection id="bilingual" title="Bilingual text"
      description="<Bi en='…' fr='…' /> renders both inline by default, FR muted. Inside a <LangCtx.Provider> it renders just one — that's how the title bar's EN/FR toggle works.">
      <div className="row-vstack">
        <div className="lib-cap">Inline (default)</div>
        <div style={{ fontSize: 14 }}>
          <Bi en="Privacy first. Security in service." fr="La confidentialité d'abord. La sécurité au service." />
        </div>
        <div className="lib-cap" style={{ marginTop: 12 }}>Stacked</div>
        <div style={{ fontSize: 14 }}>
          <Bi mode="stack" en="Continue" fr="Continuer" />
        </div>
        <div className="lib-cap" style={{ marginTop: 12 }}>Inside a language provider</div>
        <div className="row" style={{ gap: 16 }}>
          <div>
            <div className="lib-cap" style={{ marginBottom: 4 }}>EN only</div>
            <LangCtx.Provider value="en">
              <Button variant="secondary" icon="shield-check"><Bi en="Vault secured" fr="Coffre sécurisé" /></Button>
            </LangCtx.Provider>
          </div>
          <div>
            <div className="lib-cap" style={{ marginBottom: 4 }}>FR only</div>
            <LangCtx.Provider value="fr">
              <Button variant="secondary" icon="shield-check"><Bi en="Vault secured" fr="Coffre sécurisé" /></Button>
            </LangCtx.Provider>
          </div>
        </div>
      </div>
    </LibSection>
  );
}

function LibOverlays({ pushToast }) {
  const [dlg, setDlg] = useState(false);
  const [drw, setDrw] = useState(false);
  const [confirm, setConfirm] = useState(false);
  return (
    <LibSection id="overlays" title="Dialogs & drawers"
      description="Solid paper-bright overlays, no glass. Dialogs animate from a 0.99 scale; drawers slide in 240ms from the right with a soft scrim.">
      <div className="row">
        <Button variant="secondary" icon="info" onClick={() => setDlg(true)}>Open dialog</Button>
        <Button variant="secondary" icon="users-plus" onClick={() => setDrw(true)}>Open drawer</Button>
        <Button variant="danger" icon="trash" onClick={() => setConfirm(true)}>Destructive confirm</Button>
      </div>

      <Dialog open={dlg} onClose={() => setDlg(false)}
        title={<Bi en="Rotate this device's keys?" fr="Alterner les clés de l'appareil ?" />}
        description={<Bi
          en="The current key pair will be retired and a new one provisioned from the HSM. Active sessions will be re-authenticated."
          fr="La paire actuelle sera retirée et une nouvelle générée depuis le HSM. Les sessions actives seront ré-authentifiées." />}
        footer={<>
          <Button variant="ghost" onClick={() => setDlg(false)}><Bi en="Cancel" fr="Annuler" /></Button>
          <Button variant="primary" icon="rotate" kbd="⏎" onClick={() => { setDlg(false); pushToast({ tone: "success", title: "Key rotation queued.", description: "marie-vaultdrive · ETA 30s" }); }}>
            <Bi en="Rotate now" fr="Alterner" />
          </Button>
        </>}
      >
        <Field label={<Bi en="Confirm device ID" fr="Confirmer l'ID" />} hint={<Bi en="Type the device's short ID below to confirm." fr="Saisir l'identifiant court ci-dessous." />}>
          <Input mono placeholder="vd-0042" />
        </Field>
      </Dialog>

      <Drawer open={drw} onClose={() => setDrw(false)} title={<Bi en="Invite a teammate" fr="Inviter un coéquipier" />}
        footer={<>
          <Button variant="ghost" onClick={() => setDrw(false)}><Bi en="Cancel" fr="Annuler" /></Button>
          <Button variant="primary" icon="users-plus" onClick={() => { setDrw(false); pushToast({ tone: "info", title: "Invitation sent.", description: "patrick@vaultwares.com" }); }}>
            <Bi en="Send invite" fr="Envoyer" />
          </Button>
        </>}
      >
        <div className="row-vstack" style={{ gap: 16 }}>
          <Field label={<Bi en="Email" fr="Courriel" />} num="01">
            <Input type="email" placeholder="name@vaultwares.com" />
          </Field>
          <Field label={<Bi en="Role" fr="Rôle" />} num="02" hint={<Bi en="Roles can be changed later." fr="Le rôle peut être modifié plus tard." />}>
            <RadioGroup value="member" onChange={() => {}}
              options={[
                { value: "admin",  label: <span><Bi en="Admin" fr="Admin" /> · <span className="mono muted">read + write + manage</span></span> },
                { value: "member", label: <span><Bi en="Member" fr="Membre" /> · <span className="mono muted">read + write</span></span> },
                { value: "audit",  label: <span><Bi en="Audit" fr="Audit" /> · <span className="mono muted">read-only</span></span> },
              ]}
            />
          </Field>
          <Toggle on={true}><Bi en="Require hardware key on first login" fr="Exiger une clé matérielle à la 1re connexion" /></Toggle>
        </div>
      </Drawer>

      <Dialog open={confirm} onClose={() => setConfirm(false)}
        title={<Bi en="Remove this device?" fr="Retirer cet appareil ?" />}
        description={<Bi
          en="The encrypted volume will remain on the device, but it will lose access to this workspace. This cannot be undone."
          fr="Le volume chiffré reste sur l'appareil, mais perd l'accès à cet espace. Action irréversible." />}
        footer={<>
          <Button variant="ghost" onClick={() => setConfirm(false)}><Bi en="Cancel" fr="Annuler" kbd="Esc" /></Button>
          <Button variant="danger" icon="trash" onClick={() => { setConfirm(false); pushToast({ tone: "danger", title: "Device removed.", description: "marie-iphone" }); }}>
            <Bi en="Remove device" fr="Retirer l'appareil" />
          </Button>
        </>}
      />
    </LibSection>
  );
}

/* ──────────────────────────────────────────────────────────────────────────
   ROOT
   ────────────────────────────────────────────────────────────────────────── */

function App() {
  const [tab, setTab] = useState("devices");
  const [lang, setLang] = useState("en");
  const [selected, setSelected] = useState("hsm-net-01");
  const [invite, setInvite] = useState(false);
  const [confirm, setConfirm] = useState(false);

  const { toasts, push, dismiss } = useToasts();

  return (
    <LangCtx.Provider value={lang}>
      <div className="page">
        <div className="page-rail">
          <div className="kit-intro">
            <div>
              <div className="lib-cap" style={{ marginBottom: 8 }}>VaultWares · UI kit · v0.1</div>
              <h1>
                <Bi
                  en="A calm instrument, not a website."
                  fr="Un instrument calme, pas un site web."
                />
              </h1>
            </div>
            <div className="meta">
              <Bi
                en="React + Tailwind-flavored CSS. Hairlines, paper layering, monospace metadata. No glass, no infinite motion. Built to port to PySide6 (QSS) and WinUI3 (XAML) — every effect is a simple shape, fill, or 1px border."
                fr="React + CSS façon Tailwind. Hairlines, papier en couches, métadonnées monospace. Pas de verre, pas d'animation continue. Pensé pour porter vers PySide6 (QSS) et WinUI3 (XAML) — chaque effet est une forme simple, un remplissage ou un trait 1 px."
              />
            </div>
          </div>

          {/* ── App shell ── */}
          <div className="app">
            <TitleBar
              tab={tab}
              setTab={setTab}
              lang={lang}
              setLang={setLang}
              onCommand={() => push({ tone: "info", title: "Command palette", description: "⌘K · Open a fast jump-to surface" })}
            />
            <div className={`workspace ${!selected ? "no-rail" : ""}`}>
              <Sidebar />
              <DevicesPage
                selected={selected}
                setSelected={setSelected}
                openInvite={() => setInvite(true)}
                openConfirm={() => setConfirm(true)}
                pushToast={push}
              />
              {selected && (
                <DetailRail
                  deviceId={selected}
                  onClose={() => setSelected(null)}
                  openConfirm={() => setConfirm(true)}
                />
              )}
            </div>
            <StatusBar />
          </div>

          {/* ── Library section ── */}
          <div className="library">
            <div className="lib-head">
              <div className="lib-cap" style={{ marginBottom: 8 }}>Component library</div>
              <h2><Bi en="Every primitive, isolated." fr="Chaque primitive, isolée." /></h2>
              <p style={{ marginTop: 6 }}>
                <Bi
                  en="The shell above uses these. Each tile shows the component in its calm default state — copy the JSX in components.jsx and pull from the same vault tokens."
                  fr="L'interface au-dessus les utilise. Chaque tuile montre la primitive dans son état calme — copiez le JSX dans components.jsx et utilisez les mêmes jetons."
                />
              </p>
            </div>

            <div className="lib-note">
              <strong><Bi en="On portability." fr="À propos de la portabilité." /></strong>{" "}
              <Bi
                en="Every visual choice here ports to QSS/PySide6 and to XAML/WinUI3. There are no SVG-only effects, no backdrop-filters, no complex gradients. Depth comes from value, not blur. The Bilingual component compiles to two strings; render whichever one the active locale picks."
                fr="Chaque choix visuel ici se transpose en QSS/PySide6 et en XAML/WinUI3. Aucun effet SVG-only, pas de backdrop-filter, pas de dégradé complexe. La profondeur vient de la valeur, pas du flou."
              />
            </div>

            <LibButtons />
            <LibInputs />
            <LibToggles />
            <LibStatus />
            <LibCards />
            <LibBanners pushToast={push} />
            <LibForm pushToast={push} />
            <LibBilingual />
            <LibOverlays pushToast={push} />
          </div>
        </div>

        {/* Invite drawer + confirm dialog driven from the shell */}
        <Drawer open={invite} onClose={() => setInvite(false)} title={<Bi en="Add a device" fr="Ajouter un appareil" />}
          footer={<>
            <Button variant="ghost" onClick={() => setInvite(false)}><Bi en="Cancel" fr="Annuler" /></Button>
            <Button variant="primary" icon="plus" onClick={() => { setInvite(false); push({ tone: "success", title: "Device pairing started.", description: "Waiting for VaultDrive…" }); }}>
              <Bi en="Start pairing" fr="Démarrer" />
            </Button>
          </>}
        >
          <div className="row-vstack" style={{ gap: 14 }}>
            <Banner tone="info"><Bi en="Pairing is local: no key material leaves your device." fr="L'appariement est local : aucune clé ne quitte votre appareil." /></Banner>
            <Field label={<Bi en="Device type" fr="Type d'appareil" />} num="01">
              <RadioGroup value="vd" onChange={() => {}} options={[
                { value: "vd",  label: <span><Bi en="VaultDrive" fr="VaultDrive" /> · <span className="mono muted">USB-C</span></span> },
                { value: "vs",  label: <span><Bi en="VaultScan"  fr="VaultScan" />  · <span className="mono muted">biometric</span></span> },
                { value: "host", label: <span><Bi en="Host with VaultCrypt" fr="Hôte VaultCrypt" /> · <span className="mono muted">software</span></span> },
              ]} />
            </Field>
            <Field label={<Bi en="Pairing code" fr="Code d'appariement" />} num="02" hint={<Bi en="Found on the device's status screen." fr="Disponible sur l'écran d'état de l'appareil." />}>
              <Input mono placeholder="0000-0000-0000-0000" />
            </Field>
            <Toggle on={true}><Bi en="Push device to this workspace's policy" fr="Appliquer la politique de cet espace" /></Toggle>
          </div>
        </Drawer>

        <Dialog open={confirm} onClose={() => setConfirm(false)}
          title={<Bi en="Remove this device?" fr="Retirer cet appareil ?" />}
          description={<Bi
            en="The encrypted volume stays on the device, but loses access to this workspace. This cannot be undone."
            fr="Le volume chiffré reste sur l'appareil, mais perd l'accès à l'espace. Action irréversible." />}
          footer={<>
            <Button variant="ghost" onClick={() => setConfirm(false)}><Bi en="Cancel" fr="Annuler" /></Button>
            <Button variant="danger" icon="trash" onClick={() => { setConfirm(false); push({ tone: "danger", title: "Device removed.", description: selected }); setSelected(null); }}>
              <Bi en="Remove device" fr="Retirer l'appareil" />
            </Button>
          </>}
        />

        <ToastStack toasts={toasts} dismiss={dismiss} />
      </div>
    </LangCtx.Provider>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
