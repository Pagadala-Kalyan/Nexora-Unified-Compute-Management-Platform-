from pathlib import Path
from docx import Document

p = Path(r"C:\Users\KALYAN PAGADALA\Desktop\Nexora-Unified-Compute-Management-Platform-\Nexora_PBC_Report\Nexora_PBC_Project_Report_Final.docx")
d = Document(p)

def replace_exact(old, new):
    for para in d.paragraphs:
        if para.text.strip() == old:
            for run in para.runs:
                run.text = ''
            para.runs[0].text = new
            return
    raise ValueError(old)

# Temporary labels avoid collisions while preserving captions in visual order.
replace_exact('Table 2.2: Core concepts, Nexora adaptation and design position', 'Table TMP: Core concepts, Nexora adaptation and design position')
replace_exact('Table 2.1: Core concepts mapped to Nexora', 'Table 2.2: Core concepts mapped to Nexora')
replace_exact('Table TMP: Core concepts, Nexora adaptation and design position', 'Table 2.1: Core concepts, Nexora adaptation and design position')

replace_exact('Listing 4.1: Condensed session-validation behavior derived from `current_user`', 'Listing 4.2: Condensed session-validation behavior derived from `current_user`')
replace_exact('Figure 4.1: Detailed eligibility, scoring and dispatch sequence', 'Figure 4.3: Detailed eligibility, scoring and dispatch sequence')
replace_exact('Figure 4.2: Artifact upload, validation, provider transfer and output ownership flow', 'Figure 4.4: Artifact upload, validation, provider transfer and output ownership flow')
replace_exact('Figure 4.3: Wallet creation, reservation, settlement, refund and simulated purchase flow', 'Figure 4.5: Wallet creation, reservation, settlement, refund and simulated purchase flow')
replace_exact('Figure 4.4: Remote streaming session, MediaMTX authorization and provider FFmpeg pathway', 'Figure 4.6: Remote streaming session, MediaMTX authorization and provider FFmpeg pathway')
replace_exact('Figure 4.3: Optional MediaMTX and FFmpeg remote streaming architecture', 'Figure 4.7: Optional MediaMTX and FFmpeg remote streaming architecture')

replace_exact('Figure 5.3: Local, hosted and media deployment topology', 'Figure 5.2: Local, hosted and media deployment topology')
replace_exact('Figure 5.2: Documented but unverified deployment topology', 'Figure 5.3: Documented but unverified deployment topology')
d.save(p)
