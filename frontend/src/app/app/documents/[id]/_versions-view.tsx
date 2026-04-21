"use client";

import {
  type DocumentLite,
  TriggerForm,
  useDocumentJobs,
  VersionList,
} from "../../_components/versions";

export function DocumentVersions({ doc }: { doc: DocumentLite }) {
  const [jobs, refetch] = useDocumentJobs(doc.id);

  return (
    <section className="rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 overflow-hidden">
      <div className="px-5 py-4 border-b border-zinc-200 dark:border-zinc-800">
        <h2 className="text-base font-medium">Translations</h2>
        <p className="text-xs text-zinc-500 mt-1">
          Each version is an independent translation of this document. Start a
          new one below; download any finished version directly.
        </p>
      </div>

      <TriggerForm doc={doc} onDone={refetch} />

      {jobs !== null && <VersionList jobs={jobs} onChange={refetch} />}
    </section>
  );
}
