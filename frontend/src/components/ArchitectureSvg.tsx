export function ArchitectureSvg() {
  return (
    <svg
      viewBox="0 0 760 380"
      xmlns="http://www.w3.org/2000/svg"
      className="block max-w-full h-auto mx-auto"
      aria-label="System architecture diagram"
    >
      <defs>
        <marker
          id="arrow-arch"
          markerWidth="10"
          markerHeight="10"
          refX="9"
          refY="3"
          orient="auto"
        >
          <path d="M0,0 L0,6 L9,3 z" fill="currentColor" />
        </marker>
      </defs>
      <g className="text-muted-foreground">
        <g
          fill="var(--card)"
          stroke="var(--border)"
          strokeWidth="1.2"
        >
          <rect x="20" y="20" width="120" height="56" rx="8" />
          <rect x="20" y="300" width="120" height="56" rx="8" />
          <rect x="200" y="20" width="180" height="56" rx="8" />
          <rect x="200" y="300" width="180" height="56" rx="8" />
          <rect x="440" y="20" width="160" height="56" rx="8" />
          <rect x="440" y="200" width="160" height="60" rx="8" />
          <rect x="440" y="300" width="160" height="56" rx="8" />
          <rect x="660" y="120" width="80" height="56" rx="8" />
          <rect x="440" y="120" width="160" height="56" rx="8" />
        </g>

        <g fontFamily="inherit">
          <text x="80" y="46" fontSize="13" fontWeight="600" fill="var(--foreground)" textAnchor="middle">Citizen</text>
          <text x="80" y="62" fontSize="11" fill="var(--muted-foreground)" textAnchor="middle">/chat</text>

          <text x="290" y="46" fontSize="13" fontWeight="600" fill="var(--foreground)" textAnchor="middle">FastAPI</text>
          <text x="290" y="62" fontSize="11" fill="var(--muted-foreground)" textAnchor="middle">helpdesk.ampixa.com</text>

          <text x="520" y="46" fontSize="13" fontWeight="600" fill="var(--foreground)" textAnchor="middle">Hybrid Retrieval</text>
          <text x="520" y="62" fontSize="11" fill="var(--muted-foreground)" textAnchor="middle">tacit + gov.np</text>

          <text x="520" y="146" fontSize="13" fontWeight="600" fill="rgb(16, 185, 129)" textAnchor="middle">Tacit corpus</text>
          <text x="520" y="162" fontSize="11" fill="var(--muted-foreground)" textAnchor="middle">interview claims</text>

          <text x="700" y="146" fontSize="13" fontWeight="600" fill="rgb(56, 189, 248)" textAnchor="middle">Gov.np</text>
          <text x="700" y="162" fontSize="11" fill="var(--muted-foreground)" textAnchor="middle">SQLite + FTS5</text>

          <text x="520" y="226" fontSize="13" fontWeight="600" fill="var(--foreground)" textAnchor="middle">Composer</text>
          <text x="520" y="242" fontSize="11" fill="var(--muted-foreground)" textAnchor="middle">Gemma 4 + LoRA · k2</text>

          <text x="80" y="326" fontSize="13" fontWeight="600" fill="var(--foreground)" textAnchor="middle">Interviewee</text>
          <text x="80" y="342" fontSize="11" fill="var(--muted-foreground)" textAnchor="middle">/interview</text>

          <text x="290" y="326" fontSize="13" fontWeight="600" fill="var(--foreground)" textAnchor="middle">Audio + photos</text>
          <text x="290" y="342" fontSize="11" fill="var(--muted-foreground)" textAnchor="middle">stored, awaiting review</text>

          <text x="520" y="320" fontSize="13" fontWeight="600" fill="var(--foreground)" textAnchor="middle">Admin</text>
          <text x="520" y="336" fontSize="11" fill="var(--muted-foreground)" textAnchor="middle">Vertex transcribe</text>
          <text x="520" y="350" fontSize="11" fill="var(--muted-foreground)" textAnchor="middle">→ tacit corpus</text>
        </g>

        <g fill="none" stroke="currentColor" strokeWidth="1.4" markerEnd="url(#arrow-arch)">
          <line x1="140" y1="48" x2="200" y2="48" />
          <line x1="380" y1="48" x2="440" y2="48" />
          <line x1="520" y1="76" x2="520" y2="120" />
          <line x1="600" y1="148" x2="660" y2="148" />
          <line x1="380" y1="76" x2="380" y2="220" />
          <line x1="380" y1="220" x2="440" y2="220" />
          <line x1="290" y1="76" x2="290" y2="320" />
          <line x1="140" y1="328" x2="200" y2="328" />
          <line x1="380" y1="328" x2="440" y2="328" />
          <line x1="520" y1="300" x2="520" y2="180" />
        </g>
      </g>
    </svg>
  );
}
