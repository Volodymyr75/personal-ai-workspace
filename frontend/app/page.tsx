import Link from "next/link";

export default function Home() {
  return (
    <>
      <section className="hero">
        <p className="eyebrow">YOUR PERSONAL AI WORKSPACE</p>
        <h1>
          A place for your files.
          <br />
          <span>A foundation for what comes next.</span>
        </h1>
        <p className="intro">
          Bring everyday materials and questions into one workspace. Start with
          useful analysis, then grow into learning and automation.
        </p>
        <Link className="button" href="/workspace">
          Explore the workspace <span aria-hidden="true">↗</span>
        </Link>
      </section>
      <section className="notice" aria-label="Current availability">
        <span className="notice-label">CURRENT STAGE</span>
        <p>
          This is the foundation interface. Uploads, AI analysis and automations
          are not available yet. This page does not display live service health.
        </p>
      </section>
      <section aria-labelledby="next-heading">
        <div className="section-heading">
          <h2 id="next-heading">A clear direction</h2>
          <span>Planned workflows</span>
        </div>
        <div className="cards">
          <article>
            <span className="number">01 / ANALYZE</span>
            <h3>Files into findings</h3>
            <p>
              Upload a CSV, ask a question and revisit a saved report with
              verified calculations.
            </p>
            <span className="tag">First workflow · M1–M2</span>
          </article>
          <article>
            <span className="number">02 / LEARN</span>
            <h3>Context worth keeping</h3>
            <p>
              Turn photos and screenshots into editable language-learning
              materials, with the original close at hand.
            </p>
            <span className="tag">Later workflow</span>
          </article>
          <article>
            <span className="number">03 / UNDERSTAND</span>
            <h3>See the system grow</h3>
            <p>
              A future map will show real components and recorded changes,
              without inventing a history.
            </p>
            <span className="tag">Visualization · deferred</span>
          </article>
        </div>
      </section>
    </>
  );
}
