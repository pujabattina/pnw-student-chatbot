import { FormEvent, useState } from "react";

import { ChatOutcome, submitChatQuestion } from "../../api/chat";
import styles from "./ChatPage.module.css";

export default function ChatPage() {
  const [question, setQuestion] = useState("");
  const [outcome, setOutcome] = useState<ChatOutcome | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const trimmedQuestion = question.trim();
    if (!trimmedQuestion || isLoading) {
      return;
    }

    setIsLoading(true);
    setError(null);
    setOutcome(null);

    try {
      const result = await submitChatQuestion({ question: trimmedQuestion });
      setOutcome(result);
      setQuestion("");
    } catch (submitError) {
      const message =
        submitError instanceof Error
          ? submitError.message
          : "The chat service is temporarily unavailable. Please try again.";
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <main className={styles.page}>
      <section className={styles.card} aria-labelledby="chat-page-title">
        <p className={styles.kicker}>No login required</p>
        <h1 id="chat-page-title">PNW Student Chatbot</h1>
        <p className={styles.subtitle}>Ask a question and get a source-backed answer from PNW.</p>

        <form className={styles.form} onSubmit={handleSubmit}>
          <label className={styles.label} htmlFor="chat-question">
            Your question
          </label>
          <textarea
            id="chat-question"
            className={styles.textarea}
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            rows={4}
            placeholder="Ask about registration, financial aid, advising, or campus policies..."
            aria-label="Your question"
            maxLength={4000}
          />

          <div className={styles.actions}>
            <button className={styles.button} type="submit" disabled={isLoading || question.trim().length === 0}>
              {isLoading ? "Thinking..." : "Send"}
            </button>
          </div>
        </form>

        {isLoading ? (
          <div className={styles.status} role="status" aria-live="polite">
            Thinking...
          </div>
        ) : null}

        {error ? (
          <div className={styles.error} role="alert">
            {error}
          </div>
        ) : null}

        {outcome ? (
          <article className={styles.response}>
            {outcome.outcome === "supported" ? (
              <>
                <h2>Answer</h2>
                <p className={styles.answer}>{outcome.answer}</p>
                <div className={styles.citationBlock}>
                  <h3>Official source</h3>
                  <ul className={styles.citationList}>
                    {outcome.citations.map((citation) => (
                      <li key={citation.sourceId}>
                        <a href={citation.url} target="_blank" rel="noreferrer">
                          {citation.title}
                        </a>
                        {citation.locator ? <span> — {citation.locator}</span> : null}
                      </li>
                    ))}
                  </ul>
                </div>
              </>
            ) : null}

            {outcome.outcome === "clarification_needed" ? (
              <>
                <h2>Need one more detail</h2>
                <p>{outcome.question}</p>
                <p className={styles.meta}>Missing: {outcome.missingFields.join(", ")}</p>
              </>
            ) : null}

            {outcome.outcome === "referral" ? (
              <>
                <h2>Need a PNW office</h2>
                <p>{outcome.limitation}</p>
                <ul className={styles.referralList}>
                  {outcome.referrals.map((referral) => (
                    <li key={referral.name}>
                      {referral.url ? (
                        <a href={referral.url} target="_blank" rel="noreferrer">
                          {referral.name}
                        </a>
                      ) : (
                        referral.name
                      )}
                      {referral.email ? <span> · {referral.email}</span> : null}
                      {referral.phone ? <span> · {referral.phone}</span> : null}
                    </li>
                  ))}
                </ul>
              </>
            ) : null}
          </article>
        ) : null}
      </section>
    </main>
  );
}
