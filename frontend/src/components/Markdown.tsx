import ReactMarkdown from "react-markdown";
import remarkBreaks from "remark-breaks";

// Shared markdown renderer for legal prose (chat answers + clause reasoning).
// remark-breaks turns single newlines into <br> so the model's line breaks survive;
// the prose-legal class (index.css) styles emphasis, lists and links.
export function Markdown({ children }: { children: string }) {
  return (
    <div className="prose-legal text-on-surface">
      <ReactMarkdown remarkPlugins={[remarkBreaks]}>{children}</ReactMarkdown>
    </div>
  );
}
