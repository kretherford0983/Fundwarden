// v1.4.1 CR-023 / CR-024 / CR-025: Backup / Restore (System/About) and restore from the initialization wizard.
import { useRef, useState, type FormEvent } from "react";
import { api, getCsrf } from "../api";
import { ErrorBox, Field, GuardedForm } from "../components";
import ScheduledBackups from "./ScheduledBackups";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const mb = (n: number) => (n < 1024 * 1024 ? `${Math.max(1, Math.round(n / 1024))} KB` : `${(n / 1024 / 1024).toFixed(n < 10 * 1024 * 1024 ? 1 : 0)} MB`);

async function poll(url: string, onUpdate: (j: any) => void): Promise<any> {
  for (;;) {
    let j: any;
    try {
      j = await api.get(url);
    } catch {
      await sleep(1000); // the server may be busy swapping the data; keep asking
      continue;
    }
    onUpdate(j);
    if (j.state !== "running") return j;
    await sleep(700);
  }
}

function Steps({ job }: { job: any }) {
  if (!job) return null;
  return (
    <ol className="job-steps" aria-label="Progress">
      {job.steps_done.filter(Boolean).map((s: string) => <li key={s} className="done">✓ {s}</li>)}
      {job.state === "running" && job.step ? <li className="current" aria-current="step"><span className="spinner" aria-hidden="true" /> {job.step}…</li> : null}
    </ol>
  );
}

// ------------------------------------------------------------------ backup
export function BackupPanel() {
  const [f, setF] = useState({ passphrase: "", passphrase_confirmation: "", password: "" });
  const [err, setErr] = useState<unknown>(null);
  const [job, setJob] = useState<any>(null);
  const dl = useRef<HTMLAnchorElement>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setErr(null);
    if (f.passphrase !== f.passphrase_confirmation) { setErr(new Error("The passphrase and its confirmation do not match.")); return; }
    try {
      const j = await api.post("/api/system/backups", f);
      setJob(j);
      setF({ passphrase: "", passphrase_confirmation: "", password: "" });
      const done = await poll(`/api/system/backups/${j.id}`, setJob);
      if (done.state === "done") setTimeout(() => dl.current?.click(), 50);
    } catch (x) { setErr(x); }
  };
  const running = job?.state === "running";
  return (
    <section className="card" aria-labelledby="backup-h">
      <h2 id="backup-h">Create a backup</h2>
      <p>The backup file contains <b>everything needed to recover</b>: the database (all users, settings and financial records), every attachment and the encryption key. It is encrypted with the passphrase you choose. <code>config.toml</code> (server settings) is not included.</p>
      <div className="alert warn" role="note"><b>Keep the passphrase safe.</b> Without it the backup cannot be restored — nobody can recover a lost passphrase. Store the backup file away from this computer.</div>
      <ErrorBox error={err} />
      {!running ? (
        <GuardedForm onSubmit={submit}>
          <div className="row fields">
            <Field label="Backup passphrase" hint="At least 12 characters. A long sentence works well."><input type="password" required minLength={12} autoComplete="new-password" value={f.passphrase} onChange={(e) => setF({ ...f, passphrase: e.target.value })} /></Field>
            <Field label="Repeat the passphrase"><input type="password" required minLength={12} autoComplete="new-password" value={f.passphrase_confirmation} onChange={(e) => setF({ ...f, passphrase_confirmation: e.target.value })} /></Field>
          </div>
          <Field label="Your password" hint="Confirms that it is you."><input type="password" required autoComplete="current-password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} /></Field>
          <div className="actions left"><button className="primary" type="submit">Create backup</button></div>
        </GuardedForm>
      ) : null}
      <Steps job={job} />
      {job?.state === "failed" ? <div className="alert error" role="alert">{job.error}</div> : null}
      {job?.state === "done" ? (
        <div className="alert ok" role="status">
          Backup ready: <b>{job.result.filename}</b> ({mb(job.result.size)} · {job.result.counts.transactions} transactions, {job.result.files - 2} attachment files).{" "}
          <a ref={dl} href={`/api/system/backups/${job.id}/download`} download={job.result.filename}>Download again</a>
          <div className="hint">The file stays available for download here for one hour.</div>
        </div>
      ) : null}
    </section>
  );
}

// ------------------------------------------------------------------ restore
export function RestorePanel({ wizard = false, maxMb }: { wizard?: boolean; maxMb?: number | null }) {
  const [file, setFile] = useState<File | null>(null);
  const [f, setF] = useState({ passphrase: "", password: "", confirm: "" });
  const [err, setErr] = useState<unknown>(null);
  const [sent, setSent] = useState<number | null>(null);
  const [job, setJob] = useState<any>(null);
  const busy = sent !== null && (!job || job.state === "running");

  const upload = async (): Promise<string> => {
    const start = await api.post("/api/system/restore/uploads", { size: file!.size, filename: file!.name });
    const id: string = start.upload_id;
    const size: number = start.chunk_size;
    let off = 0;
    setSent(0);
    while (off < file!.size) {
      const part = file!.slice(off, off + size);
      let ok = false;
      for (let attempt = 0; attempt < 4 && !ok; attempt++) {
        try {
          const r = await fetch(`/api/system/restore/uploads/${id}?offset=${off}`, {
            method: "PUT", body: part, credentials: "same-origin",
            headers: { "Content-Type": "application/octet-stream", "X-CSRF-Token": getCsrf() || "" },
          });
          if (r.ok) { off = (await r.json()).received; ok = true; break; }
          const body = await r.json().catch(() => null);
          if (r.status < 500 && r.status !== 409) throw new Error(body?.error?.message || `Upload failed (${r.status}).`);
        } catch (x) {
          if (x instanceof Error && !/fetch|network|Failed/i.test(x.message)) throw x;
        }
        await sleep(1000 * (attempt + 1));
        try { off = (await api.get(`/api/system/restore/uploads/${id}`)).received; } catch { /* retry */ }
      }
      if (!ok) throw new Error("The upload was interrupted. Check the connection and start the restore again.");
      setSent(off);
    }
    return id;
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setErr(null);
    setJob(null);
    if (!file) return;
    if (maxMb && file.size > maxMb * 1024 * 1024) { setErr(new Error(`The file is larger than the allowed ${maxMb} MB.`)); return; }
    try {
      const id = await upload();
      const body: any = { passphrase: f.passphrase };
      if (!wizard) { body.password = f.password; body.confirm = f.confirm; }
      const j = await api.post(`/api/system/restore/uploads/${id}/start`, body);
      setJob(j);
      const done = await poll(`/api/system/restore/jobs/${j.id}`, setJob);
      if (done.state === "done") setTimeout(() => window.location.assign("/"), 4000);
      else setSent(null);
    } catch (x) {
      setErr(x);
      setSent(null);
    }
  };

  return (
    <section className={wizard ? "" : "card"} aria-labelledby="restore-h">
      <h2 id="restore-h">Restore from a backup</h2>
      {wizard ? (
        <p>Set this installation up from a PennyWarden backup (<code>.fmbak</code>) instead of creating a new organization. Everything in the backup — users and their passwords, two-step verification, all financial data and attachments — is restored. Afterwards sign in with an account from the backup.</p>
      ) : (
        <div className="alert warn" role="note"><b>This replaces all current data</b> — users, financial records and attachments — with the contents of the backup. Everyone is signed out. The current data is kept as a safety copy (<code>pre-restore</code> folder in the data directory; only the latest copy is kept).</div>
      )}
      <ErrorBox error={err} />
      {!busy && job?.state !== "done" ? (
        <GuardedForm onSubmit={submit}>
          <Field label="Backup file (.fmbak)"><input type="file" required accept=".fmbak" onChange={(e) => setFile(e.target.files?.[0] || null)} /></Field>
          <Field label="Backup passphrase"><input type="password" required autoComplete="off" value={f.passphrase} onChange={(e) => setF({ ...f, passphrase: e.target.value })} /></Field>
          {!wizard ? (
            <>
              <Field label="Your password"><input type="password" required autoComplete="current-password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} /></Field>
              <Field label="Type RESTORE to confirm"><input required autoComplete="off" value={f.confirm} onChange={(e) => setF({ ...f, confirm: e.target.value })} /></Field>
            </>
          ) : null}
          <div className="actions left"><button className="primary" type="submit" disabled={!wizard && f.confirm !== "RESTORE"}>Restore</button></div>
        </GuardedForm>
      ) : null}
      {sent !== null && file ? (
        <div className="upload-progress">
          <label>{sent >= file.size ? "Uploaded" : "Uploading"} {file.name}: {mb(Math.min(sent, file.size))} of {mb(file.size)}
            <progress max={file.size} value={Math.min(sent, file.size)} /></label>
        </div>
      ) : null}
      <Steps job={job} />
      {job?.state === "failed" ? <div className="alert error" role="alert">{job.error}</div> : null}
      {job?.state === "done" ? (
        <div className="alert ok" role="status">
          Restore complete — {job.result.workspace}, backup from {new Date(job.result.backup_created_at).toLocaleString()}. The application restarted with the restored data. Taking you to the sign-in page… <a href="/">Sign in now</a>
        </div>
      ) : null}
    </section>
  );
}

export function BackupRestore({ maxMb }: { maxMb?: number | null }) {
  const [tab, setTab] = useState<"backup" | "scheduled" | "restore">("backup");
  return (
    <div className="backup-restore">
      <h2>Backup / Restore</h2>
      <div role="tablist" className="row">
        <button role="tab" aria-selected={tab === "backup"} className={tab === "backup" ? "primary" : ""} onClick={() => setTab("backup")}>Backup</button>
        <button role="tab" aria-selected={tab === "scheduled"} className={tab === "scheduled" ? "primary" : ""} onClick={() => setTab("scheduled")}>Scheduled</button>
        <button role="tab" aria-selected={tab === "restore"} className={tab === "restore" ? "primary" : ""} onClick={() => setTab("restore")}>Restore</button>
      </div>
      {tab === "backup" ? <BackupPanel /> : tab === "scheduled" ? <ScheduledBackups /> : <RestorePanel maxMb={maxMb} />}
    </div>
  );
}
