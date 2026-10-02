import type { ReactNode } from "react";
import { BookOpenText, FileSearch, MessageSquareText } from "lucide-react";
import { Brand } from "@/components/layout/Brand";

/** Split layout: product statement on the left, the form on the right (stacked on phones). */
export function AuthLayout({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) {
  return (
    <main className="auth">
      <aside className="auth__side" aria-label="About Legal Lens">
        <Brand to="/login" />
        <div>
          <p className="auth__tag">AI-powered legal research grounded in evidence.</p>
          <div className="auth__flow">
            <div className="auth__flow-item"><MessageSquareText aria-hidden="true" /><div><b>Ask</b><span>Pose a question about Indian law in plain language.</span></div></div>
            <div className="auth__flow-item"><FileSearch aria-hidden="true" /><div><b>Retrieve</b><span>Legal Lens finds the provisions and passages that matter.</span></div></div>
            <div className="auth__flow-item"><BookOpenText aria-hidden="true" /><div><b>Verify</b><span>Every claim is cited; open any source and read it yourself.</span></div></div>
          </div>
        </div>
        <p className="auth__foot">Legal information for research and education. Not legal advice.</p>
      </aside>
      <div className="auth__main">
        <div className="auth__card">
          <div className="auth__brand-mobile"><Brand asLink={false} /></div>
          <div>
            <h1 className="auth__title">{title}</h1>
            <p className="auth__sub">{subtitle}</p>
          </div>
          {children}
        </div>
      </div>
    </main>
  );
}
