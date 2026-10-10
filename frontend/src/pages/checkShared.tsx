/** 2.0.0 (#157, #160, #162): pieces shared by the check setup screen and the print screen - the check preview drawn
 * to scale with the built-in fonts, the pattern input with variable autocomplete, and browser print instructions. */
import { useEffect, useMemo, useRef, useState } from "react";

export type FontInfo = { key: string; label: string; descent: number; descent_bold: number; cap_height: number };
export type Variable = { name: string; description: string };
export const FIELD_LABELS: Record<string, string> = {
  date: "Date", payee: "Pay to", amount_number: "Amount (number)", amount_words: "Amount (words)", memo: "Memo", signature: "Signature",
};
export const TEXT_FIELDS = ["date", "payee", "amount_number", "amount_words", "memo"];
const CLEAR_ZONE = 0.625;

/** Loads the built-in check fonts once, so the preview draws with exactly the fonts that print. */
const loaded = new Set<string>();
export function useCheckFonts(fonts: FontInfo[] | undefined) {
  const [, setN] = useState(0);
  useEffect(() => {
    if (!fonts || typeof FontFace === "undefined") return;
    for (const f of fonts) {
      for (const w of ["regular", "bold"]) {
        const id = `${f.key}-${w}`;
        if (loaded.has(id)) continue;
        loaded.add(id);
        const ff = new FontFace(`PW-${f.key}`, `url(/api/checks/fonts/${f.key}/${w})`, { weight: w === "bold" ? "700" : "400" });
        ff.load().then((x) => { (document as any).fonts.add(x); setN((n) => n + 1); }, () => undefined);
      }
    }
  }, [fonts]);
}

/** Width in inches of text in one of the built-in fonts (canvas measurement once the font has loaded). */
let ctx2d: CanvasRenderingContext2D | null = null;
export function measure(text: string, family: string, bold: boolean, sizePt: number): number {
  if (!ctx2d) ctx2d = document.createElement("canvas").getContext("2d");
  if (!ctx2d) return (text.length * 0.55 * sizePt) / 72;
  ctx2d.font = `${bold ? 700 : 400} 100px ${family}`;
  return (ctx2d.measureText(text).width / 100) * (sizePt / 72);
}

export type FieldText = { text: string; size: number; fits: boolean; shrunk?: boolean; suggestion?: string | null };

/** The check drawn to scale (inches): the stock outline (pre-printed lines, labels), the clear zone, field boxes and the
 * text as it will print. `highlight` outlines one field. */
export function CheckPreview({ cfg, fonts, texts, highlight, showBoxes = true, signature }: {
  cfg: any; fonts: FontInfo[]; texts: Record<string, FieldText> | null; highlight?: string | null; showBoxes?: boolean;
  signature?: string | null;
}) {
  const cw = cfg.stock.check_width, ch = cfg.stock.check_height;
  const fi = (k: string) => fonts.find((f) => f.key === k) || fonts[0];
  const font = (name: string) => {
    const f = cfg.fields[name];
    return { key: f.font || cfg.defaults.font, size: f.size || cfg.defaults.size, bold: !!f.bold };
  };
  const baseline = (name: string, size: number) => {
    const f = cfg.fields[name];
    const ft = font(name);
    const d = ft.bold ? fi(ft.key).descent_bold : fi(ft.key).descent;
    return f.y + f.h - (d * size) / 72;
  };
  const T = (name: string) => texts?.[name];
  const textEl = (name: string) => {
    const t = T(name);
    if (!t || name === "amount_words") return null;
    const f = cfg.fields[name];
    const ft = font(name);
    const anchor = f.align === "RIGHT" ? "end" : f.align === "CENTER" ? "middle" : "start";
    const x = f.align === "RIGHT" ? f.x + f.w : f.align === "CENTER" ? f.x + f.w / 2 : f.x;
    return (
      <text key={name} x={x} y={baseline(name, t.size)} fontFamily={`PW-${ft.key}`} fontWeight={ft.bold ? 700 : 400}
            fontSize={t.size / 72} textAnchor={anchor} fill={t.fits ? "currentColor" : "var(--red-fg, #b00)"}>{t.text}</text>
    );
  };
  const words = () => {
    const t = T("amount_words");
    if (!t) return null;
    const f = cfg.fields.amount_words;
    const ft = font("amount_words");
    const y = baseline("amount_words", t.size);
    const m = t.text.match(/^(.*) (\S+\/100)( .*)?$/);
    const w = m ? m[1] : t.text, cents = m ? m[2] + (m[3] || "") : "";
    const mid = y - (fi(ft.key).cap_height * t.size) / 72 / 2;
    const family = `PW-${ft.key}`;
    const gap = 0.06;
    const x0 = f.x + measure(w, family, ft.bold, t.size) + gap;
    const x1 = f.x + f.w - measure(cents, family, ft.bold, t.size) - gap;
    const style = cfg.amount_words.fill;
    return (
      <g fill={t.fits ? "currentColor" : "var(--red-fg, #b00)"} fontFamily={family} fontWeight={ft.bold ? 700 : 400} fontSize={t.size / 72}>
        <text x={f.x} y={y}>{w}</text>
        {x1 > x0 ? (
          <line x1={x0} x2={x1} y1={mid} y2={mid} stroke="currentColor" strokeWidth={style === "LINE" ? 0.01 : 0.012}
                strokeLinecap="round" strokeDasharray={style === "LINE" ? undefined : style === "DASHES" ? "0.055 0.02" : "0.001 0.03"} opacity={0.8} />
        ) : null}
        <text x={f.x + f.w} y={y} textAnchor="end">{cents}</text>
      </g>
    );
  };
  const sig = cfg.fields.signature;
  return (
    <svg className="check-preview" viewBox={`-0.05 -0.05 ${cw + 0.1} ${ch + 0.1}`} role="img" aria-label="Check preview drawn to scale"
         style={{ width: "100%", maxWidth: 900, display: "block", background: "var(--surface-2, #f7f5ee)" }}>
      <rect x={0} y={0} width={cw} height={ch} fill="none" stroke="currentColor" strokeWidth={0.01} opacity={0.5} />
      <rect x={0} y={ch - CLEAR_ZONE} width={cw} height={CLEAR_ZONE} fill="currentColor" opacity={0.08} />
      <text x={0.12} y={ch - CLEAR_ZONE + 0.14} fontSize={0.09} fontFamily="PW-SANS" opacity={0.6}>BANK NUMBER ZONE – NOTHING PRINTS HERE</text>
      {(cfg.stock.outline || []).map((o: any, i: number) => o.kind === "LINE" ? (
        <line key={i} x1={o.x} y1={o.y} x2={o.x2} y2={o.y2} stroke="currentColor" strokeWidth={0.008} opacity={0.45} />
      ) : o.kind === "BOX" ? (
        <rect key={i} x={o.x} y={o.y} width={o.x2 - o.x} height={o.y2 - o.y} fill="none" stroke="#b8963c" strokeWidth={0.015} opacity={0.6} />
      ) : (
        <text key={i} x={o.x} y={o.y} fontSize={(o.size || 8) / 72} fontFamily="PW-SANS" opacity={0.45}>{o.text}</text>
      ))}
      {showBoxes ? [...TEXT_FIELDS, "signature"].map((n) => {
        const f = cfg.fields[n];
        const bad = texts?.[n] && !texts[n].fits;
        return <rect key={n} x={f.x} y={f.y} width={f.w} height={f.h} fill={n === highlight ? "rgba(60,120,220,0.12)" : "none"}
                     stroke={bad ? "#c00" : n === highlight ? "#2b6cd4" : "#6a8"} strokeWidth={n === highlight ? 0.015 : 0.008}
                     strokeDasharray="0.03 0.02"><title>{FIELD_LABELS[n]}</title></rect>;
      }) : null}
      {TEXT_FIELDS.map(textEl)}
      {words()}
      <text x={sig.x + sig.w / 2} y={sig.y + sig.h / 2 + 0.04} textAnchor="middle" fontSize={0.1} fontFamily="PW-SANS" fontWeight={700} opacity={0.7}>
        {signature ?? "SIGNATURE"}
      </text>
    </svg>
  );
}

/** Text with {VARIABLES}: autocomplete after "{" (case-insensitive), descriptions shown, Enter/Tab/click inserts. */
export function PatternInput({ value, onChange, variables, label, id, placeholder, maxLength = 200 }: {
  value: string; onChange: (v: string) => void; variables: Variable[]; label: string; id: string; placeholder?: string; maxLength?: number;
}) {
  const ref = useRef<HTMLInputElement>(null);
  const [caret, setCaret] = useState(0);
  const [active, setActive] = useState(0);
  const [focus, setFocus] = useState(false);
  const open = useMemo(() => {
    const before = value.slice(0, caret);
    const i = before.lastIndexOf("{");
    if (i < 0 || before.slice(i).includes("}") || (i > 0 && before[i - 1] === "{")) return null; // "{{" is a literal brace
    const typed = before.slice(i + 1);
    if (!/^[A-Za-z_]*$/.test(typed)) return null;
    const list = variables.filter((v) => v.name.startsWith(typed.toUpperCase()));
    return list.length ? { start: i, typed, list } : null;
  }, [value, caret, variables]);
  const insert = (name: string) => {
    if (!open) return;
    const after = value.slice(caret);
    const next = value.slice(0, open.start) + `{${name}}` + (after.startsWith("}") ? after.slice(1) : after);
    onChange(next);
    const pos = open.start + name.length + 2;
    requestAnimationFrame(() => { ref.current?.setSelectionRange(pos, pos); setCaret(pos); });
  };
  const onKey = (e: React.KeyboardEvent) => {
    if (!open || !focus) return;
    if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => (a + 1) % open.list.length); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => (a - 1 + open.list.length) % open.list.length); }
    else if (e.key === "Enter" || e.key === "Tab") { e.preventDefault(); insert(open.list[Math.min(active, open.list.length - 1)].name); }
    else if (e.key === "Escape") setFocus(false);
  };
  return (
    <div className="field pattern-input">
      <label htmlFor={id}>{label}</label>
      <input id={id} ref={ref} value={value} maxLength={maxLength} placeholder={placeholder} autoComplete="off" spellCheck={false}
             role="combobox" aria-expanded={!!open && focus} aria-controls={`${id}-list`} aria-autocomplete="list"
             onChange={(e) => { onChange(e.target.value); setCaret(e.target.selectionStart || 0); setActive(0); }}
             onKeyUp={(e) => setCaret((e.target as HTMLInputElement).selectionStart || 0)}
             onClick={(e) => setCaret((e.target as HTMLInputElement).selectionStart || 0)}
             onKeyDown={onKey} onFocus={() => setFocus(true)} onBlur={() => setTimeout(() => setFocus(false), 150)} />
      {open && focus ? (
        <ul className="autocomplete" id={`${id}-list`} role="listbox">
          {open.list.map((v, i) => (
            <li key={v.name} role="option" aria-selected={i === active} className={i === active ? "active" : ""}
                onMouseDown={(e) => { e.preventDefault(); insert(v.name); }}>
              <code>{`{${v.name}}`}</code> <span className="hint">{v.description}</span>
            </li>
          ))}
        </ul>
      ) : null}
      <span className="hint">Text prints as typed; <code>{"{VARIABLE}"}</code> fills in from the transaction (type <code>{"{"}</code> for the list). Use <code>{"{{"}</code> and <code>{"}}"}</code> to print a brace.</span>
    </div>
  );
}

export type Browser = "chromium" | "firefox" | "safari" | "other";
export function detectBrowser(): Browser {
  const ua = navigator.userAgent;
  if (/Firefox\//.test(ua)) return "firefox";
  if (/Edg\/|Chrome\/|Chromium\//.test(ua)) return "chromium";
  if (/Safari\//.test(ua)) return "safari";
  return "other";
}

/** The print settings that matter for the detected browser (#162). */
export function BrowserTips({ singleFeed }: { singleFeed?: boolean }) {
  const b = detectBrowser();
  return (
    <div className="alert info browser-tips" role="note">
      <strong>Print settings</strong>
      {b === "chromium" ? (
        <ul>
          <li>Chrome, Brave or Edge: set <b>Scale</b> to <b>Actual size</b> (or Custom 100) – not "Fit to printable area".</li>
          <li>Check the <b>Paper size</b> the dialog picked{singleFeed ? " and choose the manual-feed tray" : ""}.</li>
          <li>If you saved a printer profile in your printer driver, use <b>Print using system dialog</b> (Ctrl+Shift+P) to pick it.</li>
        </ul>
      ) : b === "firefox" ? (
        <ul>
          <li>Firefox: set <b>Scale</b> to <b>100%</b> and turn off <b>Fit to page width</b>.</li>
          <li>Check the paper size{singleFeed ? " and the manual-feed tray" : ""} in the print dialog.</li>
        </ul>
      ) : b === "safari" ? (
        <ul>
          <li>Safari: set <b>Scale</b> to <b>100%</b>, and turn off <b>Auto-rotate</b> and <b>Scale to fit</b>.</li>
          <li>Check the paper size{singleFeed ? " and the manual-feed tray" : ""}.</li>
        </ul>
      ) : (
        <ul><li>Print at <b>100% / Actual size</b>. If your browser can't, download the PDF and print it from a PDF app.</li></ul>
      )}
      <p className="hint">Every test page has a 5-inch line: if it isn't exactly 5 inches, the scale is wrong. If the browser can't print at actual size,
        download the PDF and print it from Adobe Reader, Preview or another PDF app.</p>
    </div>
  );
}

/** Opens a generated PDF: a link to open it in a new tab (to print) and one to download it. */
export function PdfLinks({ pdf, label = "Open to print" }: { pdf: { url: string; name: string } | null; label?: string }) {
  if (!pdf) return null;
  return (
    <span className="pdf-links">
      <a className="button primary" href={pdf.url} target="_blank" rel="noopener">{label}</a>
      <a className="button" href={pdf.url} download={pdf.name}>Download PDF</a>
    </span>
  );
}

export function usePdf() {
  const [pdf, setPdfState] = useState<{ url: string; name: string } | null>(null);
  const set = (blob: Blob | null, name = "check.pdf") => {
    setPdfState((old) => {
      if (old) URL.revokeObjectURL(old.url);
      return blob ? { url: URL.createObjectURL(blob), name } : null;
    });
  };
  useEffect(() => () => { if (pdf) URL.revokeObjectURL(pdf.url); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  return [pdf, set] as const;
}

export function inches(v: number) { return `${v.toFixed(3)}"`; }
