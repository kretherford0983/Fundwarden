// v1.4.1 CR-016: audit review signature page options on the End of Year Audit report.
import { useEffect, useState } from "react";
import { api } from "../api";
import { EntityPicker, ErrorBox } from "../components";

export type Signer = { entity_id: string; title: string };
export type SigState = { on: boolean; choice: string; custom: string; signers: Signer[] };
/** 1.6.7: when a signer is picked, their saved position becomes the title - unless a title was typed by hand
 *  (a title that is empty or still equals the previous signer's position counts as not typed). */
export function positionTitle(people: any[], row: Signer, newId: string): string {
  const pos = (id: string) => (people.find((e) => String(e.id) === String(id))?.position || "") as string;
  const untouched = !row.title.trim() || row.title === pos(row.entity_id);
  return untouched ? pos(newId) : row.title;
}

export const SIG_EMPTY: SigState = { on: false, choice: "default", custom: "", signers: [{ entity_id: "", title: "" }] };

const VAR_RE = /\{([^{}]*)\}/g;
const KNOWN = ["FY", "ORG", "FYE"];

export function unknownVariables(text: string): string[] {
  const out = new Set<string>();
  for (const m of text.matchAll(VAR_RE)) if (!KNOWN.includes(m[1])) out.add(`{${m[1]}}`);
  return [...out];
}

export function signatureProblem(s: SigState): string | null {
  if (s.choice === "custom") {
    if (!s.custom.trim()) return "Enter the wording for the signature page.";
    const bad = unknownVariables(s.custom);
    if (bad.length) return `Unknown variable(s): ${bad.join(", ")}. Use {FY}, {ORG} or {FYE}.`;
  }
  if (s.signers.some((x) => !x.entity_id && x.title.trim())) return "A title was entered without choosing a signer.";
  if (s.signers.some((x) => x.title.length > 60)) return "A signer title may be at most 60 characters.";
  const ids = s.signers.map((x) => x.entity_id).filter(Boolean);
  if (new Set(ids).size !== ids.length) return "Each signer can be listed only once.";
  return null;
}

export function SignatureOptions({ sig, setSig, preview: previewHref }: { sig: SigState; setSig: (s: SigState) => void; preview?: string | null }) {
  const [tpl, setTpl] = useState<any>(null);
  const [people, setPeople] = useState<any[]>([]);
  const [err, setErr] = useState<unknown>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const load = () => api.get("/api/reports/signature-templates").then(setTpl, setErr);
  useEffect(() => {
    if (!sig.on || tpl) return;
    load();
    api.get("/api/entities").then((es: any[]) => setPeople(es.filter((e) => e.entity_type === "INDIVIDUAL" && !e.is_system && e.active !== false)), setErr);
  }, [sig.on]); // eslint-disable-line react-hooks/exhaustive-deps

  const set = (patch: Partial<SigState>) => setSig({ ...sig, ...patch });
  const saveCustom = async () => {
    setErr(null);
    setSaved(null);
    try {
      const r = await api.post("/api/reports/signature-templates", { text: sig.custom });
      await load();
      set({ choice: String(r.id) });
      setSaved("Wording saved for future use.");
    } catch (e) { setErr(e); }
  };
  const remove = async (id: number) => {
    setErr(null);
    setSaved(null);
    try {
      await api.delete(`/api/reports/signature-templates/${id}`);
      await load();
      if (sig.choice === String(id)) set({ choice: "default" });
    } catch (e) { setErr(e); }
  };
  const full = tpl && tpl.saved.length >= tpl.max_saved;
  const preview = sig.choice === "default" ? tpl?.default.text : tpl?.saved.find((t: any) => String(t.id) === sig.choice)?.text;

  return (
    <fieldset className="sig-options">
      <legend className="sr">Signature page</legend>
      <label className="check"><input type="checkbox" checked={sig.on} onChange={(e) => set({ on: e.target.checked })} /> Include audit review signature page</label>
      {sig.on ? (
        <div className="sig-body">
          <p className="hint">Added as the last page: a blank date line, the wording below, and a signature line for each signer. Variables: <code>{"{FY}"}</code> Fiscal Year dates, <code>{"{ORG}"}</code> organization, <code>{"{FYE}"}</code> Fiscal Year end date.</p>
          <ErrorBox error={err} />
          {saved ? <p className="ok-text" role="status">{saved}</p> : null}
          {!tpl ? <p className="hint">Loading…</p> : (
            <>
              <div role="radiogroup" aria-label="Wording options" className="sig-choices">
                <label className="check"><input type="radio" name="sig-choice" checked={sig.choice === "default"} onChange={() => set({ choice: "default" })} /> Default wording</label>
                {tpl.saved.map((t: any, i: number) => (
                  <div key={t.id} className="sig-saved row">
                    <label className="check"><input type="radio" name="sig-choice" checked={sig.choice === String(t.id)} onChange={() => set({ choice: String(t.id) })} /> Saved wording {i + 1}: <span className="muted">{t.text.length > 70 ? t.text.slice(0, 70) + "…" : t.text}</span></label>
                    <button type="button" className="small" aria-label={`Delete saved wording ${i + 1}`} onClick={() => remove(t.id)}>Delete</button>
                  </div>
                ))}
                <label className="check"><input type="radio" name="sig-choice" checked={sig.choice === "custom"} onChange={() => set({ choice: "custom" })} /> New wording…</label>
              </div>
              {sig.choice === "custom" ? (
                <div className="field">
                  <label className="field-inner">
                    <span className="field-label">Signature page wording</span>
                    <textarea rows={6} maxLength={3000} value={sig.custom} onChange={(e) => { setSaved(null); set({ custom: e.target.value }); }} placeholder="We, the Trustees of {ORG}, have conducted an internal audit … for the fiscal year {FY} …" />
                  </label>
                  <div className="row">
                    <button type="button" onClick={saveCustom} disabled={!!full || !sig.custom.trim() || unknownVariables(sig.custom).length > 0}>Save for future use</button>
                    {full ? <span className="hint">{tpl.max_saved} wordings are saved — delete one to save another.</span> : <span className="hint">{tpl.saved.length} of {tpl.max_saved} saved.</span>}
                  </div>
                </div>
              ) : (
                <blockquote className="sig-preview" aria-label="Selected wording">{preview}</blockquote>
              )}
            </>
          )}
          <h3>Signers (up to 5)</h3>
          {sig.signers.map((x, i) => (
            <div key={i} className="sig-signer row">
              <div className="grow"><EntityPicker label={`Signer ${i + 1}`} entities={people} value={x.entity_id} onChange={(id) => set({ signers: sig.signers.map((y, j) => (j === i ? { ...y, entity_id: id, title: positionTitle(people, y, id) } : y)) })} /></div>
              <label className="field-inner"><span className="field-label">Title (optional)</span><input aria-label={`Signer ${i + 1} title`} maxLength={60} value={x.title} placeholder="e.g. Trustee" onChange={(e) => set({ signers: sig.signers.map((y, j) => (j === i ? { ...y, title: e.target.value } : y)) })} /></label>
              {sig.signers.length > 1 ? <button type="button" className="small" aria-label={`Remove signer ${i + 1}`} onClick={() => set({ signers: sig.signers.filter((_, j) => j !== i) })}>Remove</button> : null}
            </div>
          ))}
          {sig.signers.length < 5 ? <button type="button" className="small" onClick={() => set({ signers: [...sig.signers, { entity_id: "", title: "" }] })}>+ Add signer</button> : null}
          <p className="hint">Signers are individual Entities. With no signer chosen, three blank "Name and title" lines are printed.</p>
          {previewHref ? (
            <p><a className="button" href={previewHref} target="_blank" rel="noopener">Preview signature page</a> <span className="hint">Opens just this page as a PDF — view or print it without generating the whole report.</span></p>
          ) : null}
        </div>
      ) : null}
    </fieldset>
  );
}
