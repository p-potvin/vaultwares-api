/* global React */
const { useState, useEffect, useRef, useCallback, createContext, useContext } = React;

/* ──────────────────────────────────────────────────────────────────────────
   Icon set — a small Lucide-aligned inline SVG library.
   stroke 1.75 to match nearby type weight; never filled (the brand mark is).
   ────────────────────────────────────────────────────────────────────────── */

const ICONS = {
  "chevron-down":  "M6 9l6 6 6-6",
  "chevron-up":    "M18 15l-6-6-6 6",
  "chevron-right": "M9 18l6-6-6-6",
  "chevron-left":  "M15 18l-6-6 6-6",
  "x":             "M18 6L6 18 M6 6l12 12",
  "check":         "M20 6L9 17l-5-5",
  "search":        "M11 11m-8 0a8 8 0 1 0 16 0a8 8 0 1 0 -16 0 M21 21l-4.35-4.35",
  "settings":      "M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0z",
  "plus":          "M12 5v14 M5 12h14",
  "minus":         "M5 12h14",
  "more":          "M12 12m-1 0a1 1 0 1 0 2 0a1 1 0 1 0 -2 0 M19 12m-1 0a1 1 0 1 0 2 0a1 1 0 1 0 -2 0 M5 12m-1 0a1 1 0 1 0 2 0a1 1 0 1 0 -2 0",
  "eye":           "M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7z M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
  "eye-off":       "M9.88 9.88a3 3 0 1 0 4.24 4.24 M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68 M6.61 6.61A13.526 13.526 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61 M2 2l20 20",
  "shield":        "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z",
  "shield-check":  "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z M9 12l2 2 4-4",
  "lock":          "M3 11h18v11H3z M7 11V7a5 5 0 0 1 10 0v4",
  "unlock":        "M3 11h18v11H3z M7 11V7a5 5 0 0 1 9.9-1",
  "key":           "M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4",
  "hard-drive":    "M2 9h20v6H2z M6 12h.01 M10 12h.01",
  "cpu":           "M4 4h16v16H4z M9 9h6v6H9z M9 1v3 M15 1v3 M9 20v3 M15 20v3 M20 9h3 M20 14h3 M1 9h3 M1 14h3",
  "scan":          "M3 7V5a2 2 0 0 1 2-2h2 M17 3h2a2 2 0 0 1 2 2v2 M21 17v2a2 2 0 0 1-2 2h-2 M7 21H5a2 2 0 0 1-2-2v-2 M7 12h10",
  "server":        "M2 2h20v8H2z M2 14h20v8H2z M6 6h.01 M6 18h.01",
  "users":         "M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2 M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z M23 21v-2a4 4 0 0 0-3-3.87 M16 3.13a4 4 0 0 1 0 7.75",
  "file-text":     "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z M14 2v6h6 M16 13H8 M16 17H8 M10 9H8",
  "activity":      "M22 12h-4l-3 9L9 3l-3 9H2",
  "info":          "M12 12m-10 0a10 10 0 1 0 20 0a10 10 0 1 0 -20 0 M12 16v-4 M12 8h.01",
  "alert-tri":     "M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z M12 9v4 M12 17h.01",
  "alert-circle":  "M12 12m-10 0a10 10 0 1 0 20 0a10 10 0 1 0 -20 0 M12 8v4 M12 16h.01",
  "copy":          "M9 9h13v13H9z M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1",
  "external":      "M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6 M15 3h6v6 M10 14L21 3",
  "arrow-right":   "M5 12h14 M12 5l7 7-7 7",
  "arrow-left":    "M19 12H5 M12 19l-7-7 7-7",
  "filter":        "M22 3H2l8 9.46V19l4 2v-8.54L22 3z",
  "sliders":       "M4 21v-7 M4 10V3 M12 21v-9 M12 8V3 M20 21v-5 M20 12V3 M1 14h6 M9 8h6 M17 16h6",
  "refresh":       "M23 4v6h-6 M1 20v-6h6 M3.51 9a9 9 0 0 1 14.85-3.36L23 10 M20.49 15a9 9 0 0 1-14.85 3.36L1 14",
  "log-out":       "M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4 M16 17l5-5-5-5 M21 12H9",
  "help":          "M12 12m-10 0a10 10 0 1 0 20 0a10 10 0 1 0 -20 0 M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3 M12 17h.01",
  "users-plus":    "M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2 M8.5 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z M20 8v6 M23 11h-6",
  "tag":           "M20.59 13.41 13.41 20.59a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z M7 7h.01",
  "languages":     "M5 8l6 6 M4 14l6-6 2-3 M2 5h12 M7 2h1 M22 22l-5-10-5 10 M14 18h6",
  "globe":         "M12 12m-10 0a10 10 0 1 0 20 0a10 10 0 1 0 -20 0 M2 12h20 M12 2a15 15 0 0 1 4 10 15 15 0 0 1-4 10 15 15 0 0 1-4-10 15 15 0 0 1 4-10z",
  "command":       "M18 3a3 3 0 0 0-3 3v12a3 3 0 0 0 3 3 3 3 0 0 0 3-3 3 3 0 0 0-3-3H6a3 3 0 0 0-3 3 3 3 0 0 0 3 3 3 3 0 0 0 3-3V6a3 3 0 0 0-3-3 3 3 0 0 0-3 3 3 3 0 0 0 3 3h12a3 3 0 0 0 3-3 3 3 0 0 0-3-3z",
  "fingerprint":   "M6.5 18.5C4.5 16.5 4 14 4 11.5a8 8 0 0 1 16 0c0 1.5-.2 3-.5 4.5 M9.5 18.5c-1-1-1.5-2.5-1.5-4a4 4 0 0 1 8 0v.5 M14 18.5C13.5 17 13 15.5 13 14a1 1 0 0 0-2 0c0 2 1 4 2.5 6 M12 9v3",
  "list":          "M3 6h.01 M8 6h13 M3 12h.01 M8 12h13 M3 18h.01 M8 18h13",
  "grid":          "M3 3h7v7H3z M14 3h7v7h-7z M14 14h7v7h-7z M3 14h7v7H3z",
  "edit":          "M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7 M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z",
  "trash":         "M3 6h18 M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2 M10 11v6 M14 11v6",
  "rotate":        "M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8 M3 3v5h5",
  "bell":          "M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9 M13.73 21a2 2 0 0 1-3.46 0",
  "wifi":          "M5 12.55a11 11 0 0 1 14.08 0 M1.42 9a16 16 0 0 1 21.16 0 M8.53 16.11a6 6 0 0 1 6.95 0 M12 20h.01",
};

function Icon({ name, size = 16, strokeWidth = 1.75, className = "", style = {}, ...rest }) {
  const d = ICONS[name];
  if (!d) return null;
  // Some icons need multiple <path>s — split on " M" boundaries.
  const paths = d.split(/(?=\sM)/).map(s => s.trim());
  return (
    <svg
      width={size} height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      style={{ flexShrink: 0, ...style }}
      aria-hidden="true"
      {...rest}
    >
      {paths.map((pd, i) => <path key={i} d={pd} />)}
    </svg>
  );
}

/* ──────────────────────────────────────────────────────────────────────────
   Bilingual — the EN ⇄ FR text component
   <Bi en="Continue" fr="Continuer" />              (inline mode, EN | FR)
   <Bi en="Vault secured" fr="Coffre sécurisé" mode="stack" />
   <Bi en="…" fr="…" />  inside <Lang.Provider value="fr"> shows FR only.
   ────────────────────────────────────────────────────────────────────────── */

const LangCtx = createContext("en");

function Bi({ en, fr, mode = "auto" }) {
  const ctx = useContext(LangCtx);
  if (ctx === "en") return <>{en}</>;
  if (ctx === "fr") return <>{fr}</>;
  if (mode === "stack") {
    return (
      <span className="bilingual-stack">
        <span className="en">{en}</span>
        <span className="fr">{fr}</span>
      </span>
    );
  }
  // inline (default)
  return (
    <span className="bilingual">
      <span className="en">{en}</span>
      <span className="div" />
      <span className="fr">{fr}</span>
    </span>
  );
}

/* ──────────────────────────────────────────────────────────────────────────
   Kbd — keyboard hint chip
   ────────────────────────────────────────────────────────────────────────── */
function Kbd({ children }) {
  return <span className="kbd">{children}</span>;
}

/* ──────────────────────────────────────────────────────────────────────────
   Button
   ────────────────────────────────────────────────────────────────────────── */
function Button({
  variant = "secondary",
  size = "md",
  icon, trailingIcon, kbd, children,
  disabled, onClick, className = "", as = "button", ...rest
}) {
  const cls = [
    "btn",
    `btn-${variant}`,
    size === "sm" && "btn-sm",
    size === "lg" && "btn-lg",
    !children && (icon || trailingIcon) && "btn-icon",
    disabled && "is-disabled",
    className,
  ].filter(Boolean).join(" ");
  const Tag = as;
  return (
    <Tag className={cls} disabled={disabled} onClick={onClick} {...rest}>
      {icon && <Icon name={icon} size={14} className="lk" />}
      {children}
      {kbd && <Kbd>{kbd}</Kbd>}
      {trailingIcon && <Icon name={trailingIcon} size={14} className="tk" />}
    </Tag>
  );
}

/* Icon-only button — preserves a11y label */
function IconButton({ icon, label, size = "md", variant = "ghost", onClick, className = "" }) {
  return (
    <button
      className={`btn btn-${variant} btn-icon ${className}`}
      onClick={onClick}
      aria-label={label}
      title={label}
    >
      <Icon name={icon} size={14} />
    </button>
  );
}

/* ──────────────────────────────────────────────────────────────────────────
   Field — label + control wrapper
   ────────────────────────────────────────────────────────────────────────── */
function Field({ label, num, hint, error, children, required }) {
  return (
    <div className="field">
      {label && (
        <label className="field-label">
          {num && <span className="num">{num}</span>}
          <span>{label}{required && <span style={{ color: "var(--vault-burgundy)", marginLeft: 3 }}>*</span>}</span>
        </label>
      )}
      {children}
      {error
        ? <div className="field-error"><Icon name="alert-circle" size={12} />{error}</div>
        : hint && <div className="field-hint">{hint}</div>}
    </div>
  );
}

/* ──────────────────────────────────────────────────────────────────────────
   Inputs
   ────────────────────────────────────────────────────────────────────────── */
function Input({ mono, error, className = "", ...rest }) {
  const cls = ["input", mono && "mono", error && "is-error", className].filter(Boolean).join(" ");
  return <input className={cls} {...rest} />;
}

function PasswordInput({ defaultValue = "", error, ...rest }) {
  const [shown, setShown] = useState(false);
  const [val, setVal] = useState(defaultValue);
  return (
    <div className="input-pw">
      <input
        className={`input ${error ? "is-error" : ""}`}
        type={shown ? "text" : "password"}
        value={val}
        onChange={e => setVal(e.target.value)}
        {...rest}
      />
      <button className="eye" type="button" onClick={() => setShown(s => !s)} aria-label={shown ? "Hide" : "Show"} title={shown ? "Hide" : "Show"}>
        <Icon name={shown ? "eye-off" : "eye"} size={14} />
      </button>
    </div>
  );
}

function SearchInput({ placeholder = "Search…", kbd = "⌘K", ...rest }) {
  return (
    <div className="search-wrap">
      <Icon name="search" size={14} className="search-ico" />
      <input className="input" placeholder={placeholder} {...rest} />
      {kbd && <span className="input-kbd"><Kbd>{kbd}</Kbd></span>}
    </div>
  );
}

function Textarea({ error, className = "", rows = 4, ...rest }) {
  return <textarea className={`textarea ${error ? "is-error" : ""} ${className}`} rows={rows} {...rest} />;
}

function Select({ options = [], error, value, onChange, ...rest }) {
  return (
    <select className={`select ${error ? "is-error" : ""}`} value={value} onChange={onChange} {...rest}>
      {options.map(o => <option key={o.value ?? o} value={o.value ?? o}>{o.label ?? o}</option>)}
    </select>
  );
}

/* ──────────────────────────────────────────────────────────────────────────
   Toggle · Checkbox · Radio
   ────────────────────────────────────────────────────────────────────────── */
function Toggle({ on, onChange, children }) {
  return (
    <button type="button" className={`toggle ${on ? "on" : ""}`} onClick={() => onChange?.(!on)} role="switch" aria-checked={on}>
      <span className="tk" />
      {children && <span className="lab">{children}</span>}
    </button>
  );
}

function Checkbox({ on, onChange, children }) {
  return (
    <button type="button" className={`cb ${on ? "on" : ""}`} onClick={() => onChange?.(!on)} role="checkbox" aria-checked={on}>
      <span className="box">{on && <Icon name="check" size={11} strokeWidth={3} />}</span>
      {children && <span>{children}</span>}
    </button>
  );
}

function Radio({ on, onChange, children }) {
  return (
    <button type="button" className={`radio ${on ? "on" : ""}`} onClick={() => onChange?.(!on)} role="radio" aria-checked={on}>
      <span className="dot" />
      {children && <span>{children}</span>}
    </button>
  );
}

function RadioGroup({ value, onChange, options }) {
  return (
    <div className="col">
      {options.map(o => (
        <Radio key={o.value} on={value === o.value} onChange={() => onChange(o.value)}>{o.label}</Radio>
      ))}
    </div>
  );
}

/* ──────────────────────────────────────────────────────────────────────────
   Status · Badge · Tag · Avatar
   ────────────────────────────────────────────────────────────────────────── */
function Status({ tone = "secured", pulse, children }) {
  return (
    <span className="status">
      <span className={`dot ${tone} ${pulse ? "pulse" : ""}`} />
      {children}
    </span>
  );
}

function Badge({ tone = "default", children }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}

function Tag({ children, onRemove }) {
  return (
    <span className="tag">
      {children}
      {onRemove && <button className="x" onClick={onRemove} aria-label="Remove"><Icon name="x" size={11} /></button>}
    </span>
  );
}

/* Avatar — color from a seed for variety, monogram fallback */
const AV_COLORS = ["#0A2540", "#586E75", "#4A5459", "#7a5e0c", "#0d6473", "#1f6b0e", "#6b1e21"];
function avColor(seed = "") {
  let h = 0; for (const c of seed) h = (h * 31 + c.charCodeAt(0)) | 0;
  return AV_COLORS[Math.abs(h) % AV_COLORS.length];
}
function Avatar({ name = "", size = 26 }) {
  const initials = name.split(/\s+/).filter(Boolean).slice(0, 2).map(p => p[0]?.toUpperCase()).join("") || "?";
  return (
    <span className="av" style={{ width: size, height: size, background: avColor(name), fontSize: size * 0.42 }}>
      {initials}
    </span>
  );
}

/* ──────────────────────────────────────────────────────────────────────────
   CodeChip — mono inline w/ copy
   ────────────────────────────────────────────────────────────────────────── */
function CodeChip({ children, copy }) {
  const [copied, setCopied] = useState(false);
  const onCopy = () => {
    try { navigator.clipboard.writeText(copy ?? String(children)); } catch (e) {}
    setCopied(true); setTimeout(() => setCopied(false), 1400);
  };
  return (
    <span className="code-chip">
      <span>{children}</span>
      <button onClick={onCopy} aria-label="Copy" title={copied ? "Copied" : "Copy"}>
        <Icon name={copied ? "check" : "copy"} size={11} />
      </button>
    </span>
  );
}

/* ──────────────────────────────────────────────────────────────────────────
   Banner / Callout
   ────────────────────────────────────────────────────────────────────────── */
const TONE_ICONS = {
  success: "shield-check",
  warning: "alert-tri",
  danger:  "alert-circle",
  info:    "info",
  default: "info",
};
const TONE_COLORS = {
  success: "var(--vault-green)",
  warning: "var(--vault-gold)",
  danger:  "var(--vault-burgundy)",
  info:    "var(--vault-cyan)",
  default: "var(--vault-slate)",
};

function Banner({ tone = "info", title, children, actions }) {
  return (
    <div className={`banner ${tone}`}>
      <Icon name={TONE_ICONS[tone]} size={16} className="ico" style={{ color: TONE_COLORS[tone] }} />
      <div className="body">
        {title && <div><strong>{title}</strong></div>}
        <div>{children}</div>
      </div>
      {actions && <div className="actions">{actions}</div>}
    </div>
  );
}

/* ──────────────────────────────────────────────────────────────────────────
   Toast — controlled by useToasts() hook
   ────────────────────────────────────────────────────────────────────────── */
function useToasts() {
  const [toasts, setToasts] = useState([]);
  const push = useCallback((t) => {
    const id = Math.random().toString(36).slice(2, 8);
    setToasts(ts => [...ts, { id, ...t }]);
    if (t.duration !== 0) {
      setTimeout(() => setToasts(ts => ts.filter(x => x.id !== id)), t.duration ?? 4500);
    }
  }, []);
  const dismiss = useCallback(id => setToasts(ts => ts.filter(t => t.id !== id)), []);
  return { toasts, push, dismiss };
}

function ToastStack({ toasts, dismiss }) {
  return (
    <div className="toast-stack" aria-live="polite">
      {toasts.map(t => (
        <div key={t.id} className={`toast ${t.tone || ""}`}>
          <Icon name={TONE_ICONS[t.tone || "success"]} size={15} className="ico" style={{ color: TONE_COLORS[t.tone || "success"] }} />
          <div className="body">
            <div className="t">{t.title}</div>
            {t.description && <div className="d">{t.description}</div>}
          </div>
          <button className="close" onClick={() => dismiss(t.id)} aria-label="Dismiss"><Icon name="x" size={13} /></button>
        </div>
      ))}
    </div>
  );
}

/* ──────────────────────────────────────────────────────────────────────────
   Dialog · Drawer (solid paper overlays — NO glass)
   ────────────────────────────────────────────────────────────────────────── */
function Dialog({ open, onClose, title, description, children, footer, maxWidth = 460 }) {
  useEffect(() => {
    if (!open) return;
    const onKey = e => e.key === "Escape" && onClose?.();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="dialog-scrim" onClick={onClose}>
      <div className="dialog" style={{ maxWidth }} onClick={e => e.stopPropagation()}>
        <div className="dialog-head">
          <h2>{title}</h2>
          {description && <p>{description}</p>}
        </div>
        <div className="dialog-body">{children}</div>
        {footer && <div className="dialog-foot">{footer}</div>}
      </div>
    </div>
  );
}

function Drawer({ open, onClose, title, children, footer, width = 400 }) {
  useEffect(() => {
    if (!open) return;
    const onKey = e => e.key === "Escape" && onClose?.();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <>
      <div className="drawer-scrim" onClick={onClose} />
      <div className="drawer" style={{ width }}>
        <div className="drawer-head">
          <span className="ttl">{title}</span>
          <IconButton icon="x" label="Close" onClick={onClose} />
        </div>
        <div className="drawer-body">{children}</div>
        {footer && <div className="dialog-foot">{footer}</div>}
      </div>
    </>
  );
}

/* ──────────────────────────────────────────────────────────────────────────
   Export to window so other Babel scripts can use these
   ────────────────────────────────────────────────────────────────────────── */
Object.assign(window, {
  Icon, Kbd, LangCtx, Bi,
  Button, IconButton,
  Field, Input, PasswordInput, SearchInput, Textarea, Select,
  Toggle, Checkbox, Radio, RadioGroup,
  Status, Badge, Tag, Avatar, CodeChip,
  Banner,
  useToasts, ToastStack,
  Dialog, Drawer,
});
