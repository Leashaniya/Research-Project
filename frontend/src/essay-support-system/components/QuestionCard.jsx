import ReactMarkdown from 'react-markdown';
import rehypeRaw from 'rehype-raw';

export default function QuestionCard({ question }) {
  if (!question) return null;

  return (
    <div className="question-card card">
      <div className="question-text">
        <ReactMarkdown rehypePlugins={[rehypeRaw]}>
          {question.question}
        </ReactMarkdown>
      </div>

      <style>{`
        .question-card {
          margin-bottom: 1.25rem;
        }
        .question-text {
          font-size: 1.05rem;
          line-height: 1.7;
        }
        .question-text p { margin-bottom: 0.5rem; }
        .question-text code {
          background: rgba(139,92,246,0.12);
          padding: 0.15rem 0.4rem;
          border-radius: 4px;
          font-size: 0.9em;
        }
      `}</style>
    </div>
  );
}
