import Link from "next/link";

export default function Workspace() {
  return (
    <section className="hero workspace">
      <p className="eyebrow">WORKSPACE / FOUNDATION</p>
      <h1>
        Your first workflow
        <br />
        <span>starts here.</span>
      </h1>
      <p className="intro">
        CSV upload, analysis and saved results are planned for the next
        milestones. There are no active agents or file-processing tools in this
        foundation interface.
      </p>
      <div className="notice">
        <p>
          File upload is not available yet. No personal files are collected by
          this page.
        </p>
      </div>
      <Link className="button" href="/">
        Back to overview <span aria-hidden="true">↗</span>
      </Link>
    </section>
  );
}
