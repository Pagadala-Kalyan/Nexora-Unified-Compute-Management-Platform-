from pathlib import Path
from datetime import date
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(r"C:\Users\KALYAN PAGADALA\Desktop\Nexora-Unified-Compute-Management-Platform-")
OUT = ROOT / "Nexora_PBC_Report"
OUT.mkdir(exist_ok=True)
DOCX_OUT = OUT / "Nexora_PBC_Project_Report.docx"
VALIDATION_OUT = OUT / "Nexora_Report_Validation.md"
ASSETS = OUT / "assets"
ASSETS.mkdir(exist_ok=True)

NAVY = "163A5F"
BLUE = "2E75B6"
PALE = "D9EAF7"
GRAY = "F2F2F2"
DARK = "1F1F1F"

def shade(cell, color):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:fill'), color)
    tcPr.append(shd)

def set_cell_text(cell, text, bold=False, size=8.5, color=None):
    cell.text = ""
    p = cell.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    r = p.add_run(str(text))
    r.bold = bold
    r.font.name = "Times New Roman"
    r._element.rPr.rFonts.set(qn('w:ascii'), 'Times New Roman')
    r._element.rPr.rFonts.set(qn('w:hAnsi'), 'Times New Roman')
    r.font.size = Pt(size)
    if color:
        r.font.color.rgb = RGBColor.from_string(color)
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER

def set_repeat_table_header(row):
    trPr = row._tr.get_or_add_trPr()
    tblHeader = OxmlElement('w:tblHeader')
    tblHeader.set(qn('w:val'), 'true')
    trPr.append(tblHeader)

def set_cell_margins(cell, top=90, start=90, bottom=90, end=90):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcMar = tcPr.first_child_found_in('w:tcMar')
    if tcMar is None:
        tcMar = OxmlElement('w:tcMar')
        tcPr.append(tcMar)
    for m, v in [('top', top), ('start', start), ('bottom', bottom), ('end', end)]:
        node = tcMar.find(qn(f'w:{m}'))
        if node is None:
            node = OxmlElement(f'w:{m}')
            tcMar.append(node)
        node.set(qn('w:w'), str(v))
        node.set(qn('w:type'), 'dxa')

def set_font(run, size=12, bold=None, italic=None, color=None, name='Times New Roman'):
    run.font.name = name
    run._element.rPr.rFonts.set(qn('w:ascii'), name)
    run._element.rPr.rFonts.set(qn('w:hAnsi'), name)
    run.font.size = Pt(size)
    if bold is not None: run.bold = bold
    if italic is not None: run.italic = italic
    if color: run.font.color.rgb = RGBColor.from_string(color)

def add_page_number(paragraph):
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run()
    fldChar1 = OxmlElement('w:fldChar'); fldChar1.set(qn('w:fldCharType'), 'begin')
    instrText = OxmlElement('w:instrText'); instrText.set(qn('xml:space'), 'preserve'); instrText.text = ' PAGE '
    fldChar2 = OxmlElement('w:fldChar'); fldChar2.set(qn('w:fldCharType'), 'end')
    run._r.append(fldChar1); run._r.append(instrText); run._r.append(fldChar2)
    set_font(run, 10)

def set_update_fields(doc):
    settings = doc.settings.element
    node = OxmlElement('w:updateFields')
    node.set(qn('w:val'), 'true')
    settings.append(node)

def make_diagram(path, title, rows, width=1600, height=900):
    image = Image.new('RGB', (width, height), 'white')
    d = ImageDraw.Draw(image)
    try:
        font_title = ImageFont.truetype('arialbd.ttf', 42)
        font = ImageFont.truetype('arial.ttf', 26)
        font_small = ImageFont.truetype('arial.ttf', 21)
    except OSError:
        font_title = font = font_small = ImageFont.load_default()
    d.text((width//2, 30), title, fill='#163A5F', font=font_title, anchor='ma')
    y = 135
    for row in rows:
        labels = row
        n = len(labels)
        gap = 50
        box_w = min(310, (width - (n+1)*gap)//n)
        total = n*box_w + (n-1)*gap
        x = (width-total)//2
        centers = []
        for label, fill in labels:
            h = 112
            d.rounded_rectangle((x, y, x+box_w, y+h), radius=18, fill=fill, outline='#163A5F', width=3)
            words = label.split(' ')
            lines=[]; line=''
            for word in words:
                candidate = (line+' '+word).strip()
                if d.textbbox((0,0), candidate, font=font)[2] > box_w-24 and line:
                    lines.append(line); line=word
                else: line=candidate
            if line: lines.append(line)
            line_y=y+h/2-(len(lines)*15)
            for line in lines:
                d.text((x+box_w/2,line_y),line,fill='#111111',font=font,anchor='ma')
                line_y += 31
            centers.append((x+box_w/2, y+h/2))
            x += box_w+gap
        for i in range(len(centers)-1):
            a,b=centers[i],centers[i+1]
            d.line((a[0]+box_w/2,a[1],b[0]-box_w/2,b[1]),fill='#2E75B6',width=5)
            d.polygon([(b[0]-box_w/2,b[1]),(b[0]-box_w/2-18,b[1]-10),(b[0]-box_w/2-18,b[1]+10)],fill='#2E75B6')
        y += 190
    image.save(path)

def ptext(doc, text='', align=WD_ALIGN_PARAGRAPH.JUSTIFY, bold=False, italic=False, size=12, before=0, after=6, keep=False):
    p = doc.add_paragraph()
    p.alignment = align
    p.paragraph_format.space_before = Pt(before)
    p.paragraph_format.space_after = Pt(after)
    p.paragraph_format.line_spacing = 1.5
    p.paragraph_format.keep_with_next = keep
    r = p.add_run(text)
    set_font(r, size, bold, italic)
    return p

def add_heading(doc, text, level=1):
    p = doc.add_paragraph(style=f'Heading {level}')
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.space_before = Pt(14 if level == 1 else 9)
    p.paragraph_format.space_after = Pt(7)
    p.paragraph_format.keep_with_next = True
    r = p.add_run(text)
    set_font(r, 15 if level==1 else (13 if level==2 else 12), True, False, NAVY)
    return p

def bullet(doc, text, level=0):
    p = doc.add_paragraph(style='List Bullet' if level==0 else 'List Bullet 2')
    p.paragraph_format.line_spacing = 1.3
    p.paragraph_format.space_after = Pt(2)
    r=p.add_run(text); set_font(r, 11)
    return p

def code_block(doc, text):
    p=doc.add_paragraph()
    p.paragraph_format.left_indent=Inches(.25)
    p.paragraph_format.right_indent=Inches(.25)
    p.paragraph_format.space_after=Pt(7)
    p.paragraph_format.line_spacing=1.0
    shading=OxmlElement('w:shd'); shading.set(qn('w:fill'),'F2F2F2'); p._p.get_or_add_pPr().append(shading)
    for line in text.strip().split('\n'):
        r=p.add_run(line+'\n'); set_font(r,8.5,name='Consolas')
    return p

def caption(doc, kind, number, text):
    p=doc.add_paragraph()
    p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before=Pt(3); p.paragraph_format.space_after=Pt(9)
    r=p.add_run(f'{kind} {number}: {text}')
    set_font(r,10.5,True,True)
    return p

def add_table(doc, headers, rows, widths=None, font_size=8.5):
    table=doc.add_table(rows=1, cols=len(headers))
    table.style='Table Grid'; table.alignment=WD_TABLE_ALIGNMENT.CENTER
    hdr=table.rows[0]; set_repeat_table_header(hdr)
    for i,h in enumerate(headers):
        set_cell_text(hdr.cells[i],h,True,font_size,'FFFFFF'); shade(hdr.cells[i],NAVY); set_cell_margins(hdr.cells[i])
    for row in rows:
        cells=table.add_row().cells
        for i,val in enumerate(row):
            set_cell_text(cells[i],val,False,font_size)
            set_cell_margins(cells[i])
            if len(table.rows)%2==1: shade(cells[i],'F7FAFC')
    if widths:
        for row in table.rows:
            for i,w in enumerate(widths): row.cells[i].width=Inches(w)
    doc.add_paragraph().paragraph_format.space_after=Pt(2)
    return table

def add_figure(doc, path, number, text, width=6.25):
    p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(str(path), width=Inches(width))
    caption(doc,'Figure',number,text)

def pb(doc):
    doc.add_page_break()

def chapter(doc, n, title):
    pb(doc)
    p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER; p.paragraph_format.space_before=Pt(120); p.paragraph_format.space_after=Pt(18)
    r=p.add_run(f'CHAPTER {n}'); set_font(r,18,True,False,NAVY)
    p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER; p.paragraph_format.space_after=Pt(60)
    r=p.add_run(title.upper()); set_font(r,18,True,False,NAVY)
    add_heading(doc, f'CHAPTER {n} {title.upper()}', 1)

def add_toc(doc):
    pb(doc)
    p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    r=p.add_run('TABLE OF CONTENTS'); set_font(r,16,True,False,NAVY)
    ptext(doc,'The report is organized in the reference format: six chapters followed by supporting materials, references and appendices. Page numbers can be refreshed in Microsoft Word by selecting all fields and updating them.',after=10)
    entries=[
        ('Abstract',0),('Chapter 1 Introduction',0),('1.1 Background and Motivation',1),('1.2 Problem Statement',1),('1.3 Project Objectives and Scope',1),
        ('Chapter 2 Literature Review and Core Concepts',0),('2.1 Distributed Compute Orchestration',1),('2.2 Control Plane and Provider Agent Architecture',1),('2.3 Scheduling, Checkpointing and Telemetry',1),('2.4 Artifact, Streaming and Token Accounting Concepts',1),
        ('Chapter 3 System Architecture and Methodology',0),('3.1 Proposed System Architecture',1),('3.2 Module Interoperability and Data Flow',1),('3.3 Implementation Environment',1),
        ('Chapter 4 Implementation and Details',0),('4.1 Orchestration and Entry Points',1),('4.2 Authentication and Provider Management',1),('4.3 Workload Scheduling and Recovery',1),('4.4 Frontend and Realtime Communication',1),('4.5 Artifacts, Billing and Streaming',1),
        ('Chapter 5 Results and Analysis',0),('5.1 Qualitative Results',1),('5.2 Quantitative Validation Evidence',1),('5.3 Edge Cases and Limitations',1),('5.4 Security and Reliability Analysis',1),
        ('Chapter 6 Conclusion and Future Work',0),('Supporting Materials',0),('References',0),('Appendix A API and Data Model Summary',0),('Appendix B Deployment, Testing and Selected Listings',0)]
    for text,indent in entries:
        p=doc.add_paragraph(); p.paragraph_format.left_indent=Inches(0.35*indent); p.paragraph_format.space_after=Pt(2)
        r=p.add_run(text); set_font(r,11, bold=(indent==0))

def add_cover(doc):
    for _ in range(3): ptext(doc,'',align=WD_ALIGN_PARAGRAPH.CENTER,after=2)
    p=ptext(doc,'NEXORA',align=WD_ALIGN_PARAGRAPH.CENTER,bold=True,size=27,after=4); p.paragraph_format.space_before=Pt(30)
    ptext(doc,'UNIFIED COMPUTE MANAGEMENT PLATFORM',align=WD_ALIGN_PARAGRAPH.CENTER,bold=True,size=17,after=25)
    ptext(doc,'A Project Based Component Project Report',align=WD_ALIGN_PARAGRAPH.CENTER,bold=True,size=13,after=18)
    ptext(doc,'Submitted in partial fulfillment of the requirement for the PBC component of',align=WD_ALIGN_PARAGRAPH.CENTER,size=12,after=1)
    ptext(doc,'BACHELOR OF TECHNOLOGY',align=WD_ALIGN_PARAGRAPH.CENTER,bold=True,size=14,after=1)
    ptext(doc,'IN',align=WD_ALIGN_PARAGRAPH.CENTER,bold=True,size=12,after=1)
    ptext(doc,'COMPUTER SCIENCE ENGINEERING',align=WD_ALIGN_PARAGRAPH.CENTER,bold=True,size=14,after=28)
    ptext(doc,'by',align=WD_ALIGN_PARAGRAPH.CENTER,bold=True,size=12,after=8)
    for i in range(1,5): ptext(doc,f'[Student Name {i}] ([Registration Number {i}])',align=WD_ALIGN_PARAGRAPH.CENTER,size=12,after=2)
    ptext(doc,'',align=WD_ALIGN_PARAGRAPH.CENTER,after=15)
    ptext(doc,'Under the Guidance of',align=WD_ALIGN_PARAGRAPH.CENTER,bold=True,size=12,after=5)
    ptext(doc,'Dr. Nagendra Panini Challa',align=WD_ALIGN_PARAGRAPH.CENTER,bold=True,size=13,after=42)
    ptext(doc,'SCHOOL OF COMPUTER SCIENCE AND ENGINEERING',align=WD_ALIGN_PARAGRAPH.CENTER,bold=True,size=13,after=2)
    ptext(doc,'VIT-AP UNIVERSITY',align=WD_ALIGN_PARAGRAPH.CENTER,bold=True,size=13,after=2)
    ptext(doc,'AMARAVATI - 522237',align=WD_ALIGN_PARAGRAPH.CENTER,bold=True,size=12,after=2)
    ptext(doc,'October 2026',align=WD_ALIGN_PARAGRAPH.CENTER,size=12,after=0)
    pb(doc)

def add_abstract(doc):
    p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    r=p.add_run('ABSTRACT'); set_font(r,16,True,False,NAVY)
    ptext(doc, 'Nexora - Unified Compute Management Platform (UCMP) is a distributed-compute orchestration prototype that coordinates a browser dashboard, a FastAPI control plane and independently running provider agents. The project addresses the practical difficulty of discovering heterogeneous compute machines, selecting a compatible provider, dispatching a workload, observing progress and retaining a record of execution state. Rather than operating as a cloud provider, Nexora supplies an orchestration layer: provider-owned machines advertise their capacity and execute work while the control plane owns user identity, scheduling, job state, token accounting and recovery metadata.')
    ptext(doc, 'The implementation uses a static JavaScript frontend, a Python FastAPI backend with SQLAlchemy persistence, and Python provider agents using requests and psutil. Implemented source paths include user registration and JWT-backed sessions, shared-token provider registration, heartbeat telemetry, capacity and cost/reliability-aware provider selection, polling-based job dispatch, controlled workload execution, artifact handling, checkpoint storage, attempt fencing, recovery after provider heartbeat loss, a token ledger, and optional remote live-stream encoding with MediaMTX and FFmpeg. The frontend consumes REST snapshots and an authenticated WebSocket topic set for real-time updates.')
    ptext(doc, 'Evidence in this report distinguishes implementation from demonstrated behavior. Python syntax checks completed successfully and twelve frontend utility tests passed. The backend pytest suite was not run because pytest was absent from the supplied virtual environment; Docker Compose, a live provider, PostgreSQL, MediaMTX, OBS/browser capture, cloud deployment and destination streaming were not run during the audit. Consequently, the report presents Nexora as a technically substantial prototype with verified source-level behavior and limited runtime validation, not as a production-ready compute marketplace or independently verified streaming service.')
    ptext(doc,'Keywords: distributed computing, orchestration, FastAPI, provider agent, scheduling, checkpoint recovery, telemetry, WebSocket, MediaMTX, FFmpeg.',bold=True,after=0)

def build():
    doc=Document()
    sec=doc.sections[0]
    sec.top_margin=Inches(1); sec.bottom_margin=Inches(1); sec.left_margin=Inches(1); sec.right_margin=Inches(1)
    sec.page_width=Inches(8.5); sec.page_height=Inches(11)
    normal=doc.styles['Normal']; normal.font.name='Times New Roman'; normal._element.rPr.rFonts.set(qn('w:ascii'),'Times New Roman'); normal._element.rPr.rFonts.set(qn('w:hAnsi'),'Times New Roman'); normal.font.size=Pt(12)
    for style_name, size, color in [('Heading 1',15,NAVY),('Heading 2',13,NAVY),('Heading 3',12,NAVY)]:
        st=doc.styles[style_name]; st.font.name='Times New Roman'; st._element.rPr.rFonts.set(qn('w:ascii'),'Times New Roman'); st._element.rPr.rFonts.set(qn('w:hAnsi'),'Times New Roman'); st.font.size=Pt(size); st.font.bold=True; st.font.color.rgb=RGBColor.from_string(color)
    footer=sec.footer.paragraphs[0]
    add_page_number(footer)
    set_update_fields(doc)

    # Diagram assets
    make_diagram(ASSETS/'fig31_architecture.png','Nexora System Architecture',[
        [('Dashboard User', '#D9EAF7'), ('Static Frontend', '#D9EAF7'), ('FastAPI Control Plane', '#B4C7E7'), ('SQLAlchemy Store', '#D9EAD3')],
        [('Provider Agent', '#FCE4D6'), ('Hardware and FFmpeg', '#FCE4D6'), ('MediaMTX Optional', '#FFF2CC'), ('Streaming Destination', '#FFF2CC')],
    ])
    make_diagram(ASSETS/'fig32_dataflow.png','Job Submission and Data Flow',[
        [('Login and JWT', '#D9EAF7'), ('Create Job', '#D9EAF7'), ('Reserve Tokens', '#B4C7E7'), ('Schedule Provider', '#B4C7E7')],
        [('Provider Poll', '#FCE4D6'), ('Execute and Checkpoint', '#FCE4D6'), ('Persist Result', '#D9EAD3'), ('Dashboard Update', '#D9EAF7')],
    ])
    make_diagram(ASSETS/'fig33_lifecycle.png','Workload Lifecycle',[
        [('SCHEDULED', '#D9EAF7'), ('RUNNING', '#B4C7E7'), ('CHECKPOINTED', '#FFF2CC'), ('COMPLETED or FAILED', '#D9EAD3')],
        [('Provider Loss', '#FCE4D6'), ('RECOVERING', '#FCE4D6'), ('New Attempt', '#FFF2CC'), ('Fencing Check', '#D9EAF7')],
    ])
    make_diagram(ASSETS/'fig34_recovery.png','Provider Recovery Workflow',[
        [('Heartbeat Monitor', '#D9EAF7'), ('Timeout Detection', '#FCE4D6'), ('Load Latest Checkpoint', '#FFF2CC'), ('Find Compatible Provider', '#B4C7E7')],
        [('Recovery Attempt', '#D9EAD3'), ('Resume or Restart', '#D9EAF7'), ('Settle or Refund', '#FCE4D6')],
    ])
    make_diagram(ASSETS/'fig35_er.png','Nexora Data Relationships',[
        [('Users', '#D9EAF7'), ('Auth Sessions', '#D9EAF7'), ('Wallets', '#FFF2CC'), ('Token Transactions', '#FFF2CC')],
        [('Jobs', '#B4C7E7'), ('Checkpoints', '#D9EAD3'), ('Artifacts', '#D9EAD3'), ('Providers', '#FCE4D6')],
        [('Stream Sessions', '#FFF2CC'), ('Audit Events', '#F2F2F2'), ('Job Billing', '#F2F2F2')],
    ])
    make_diagram(ASSETS/'fig36_deploy.png','Deployment Topology',[
        [('Vercel Static UI', '#D9EAF7'), ('Render or Local API', '#B4C7E7'), ('SQLite or PostgreSQL', '#D9EAD3')],
        [('Provider Machine', '#FCE4D6'), ('MediaMTX Host', '#FFF2CC'), ('OBS or Browser Capture', '#FFF2CC')],
    ])
    make_diagram(ASSETS/'fig37_stream.png','Optional Remote Streaming Flow',[
        [('OBS or Browser Capture', '#D9EAF7'), ('MediaMTX Ingest', '#FFF2CC'), ('Provider FFmpeg', '#FCE4D6'), ('RTMP Destination', '#FFF2CC')],
        [('Control Plane Session', '#B4C7E7'), ('MediaMTX Auth Callback', '#D9EAD3'), ('Provider Heartbeat and Billing', '#FCE4D6')],
    ])

    add_cover(doc); add_abstract(doc); add_toc(doc)

    # Chapter 1
    chapter(doc,1,'Introduction')
    add_heading(doc,'1.1 Background and Motivation',2)
    ptext(doc,'Modern computing workloads frequently span machines with different processors, memory capacities, GPU availability, network positions and operating conditions. In small laboratories, academic groups and prototype deployments, these machines are often operated independently. A user must manually decide where work can run, verify whether a machine is available, transfer input data, observe execution, and interpret failures. This fragmented process motivates a unified orchestration layer that makes distributed compute resources visible through one control plane while preserving the provider machine as the location of execution.')
    ptext(doc,'Nexora addresses this coordination problem. The codebase implements a static browser console through which authenticated users can inspect providers, submit jobs, observe state, access billing information and configure a control-plane URL. A FastAPI backend maintains durable application state and provides the interface between users and providers. Python provider agents are responsible for inspecting their own hardware, registering capacity, reporting telemetry, polling for work and executing assigned workloads. The design therefore separates governance and state management from physical compute ownership.')
    add_heading(doc,'1.2 Problem Statement',2)
    ptext(doc,'The problem addressed by Nexora is the absence of a lightweight, source-visible workflow for coordinating heterogeneous provider resources and workloads without relying on an opaque centralized cloud platform. The project must authenticate users, register provider capacity, choose a compatible provider, reserve a controlled amount of token credit, dispatch a job, retain progress and checkpoint state, report results, and handle at least a basic provider-loss scenario. The implementation must also avoid presenting simulations as completed external integrations.')
    add_heading(doc,'1.3 Project Objectives and Scope',2)
    add_table(doc,['Objective','Source-backed realization','Status'],[
        ('Provide a web control plane','Hash-routed frontend with REST and WebSocket clients','Implemented in source'),
        ('Discover compute providers','Provider registration with hardware/system metadata','Implemented in source'),
        ('Select compatible resources','CPU/RAM/GPU/FFmpeg filters and adjusted cost comparison','Implemented in source'),
        ('Execute controlled workloads','Provider supports matrix, prime, Fibonacci, video and custom Python paths','Implemented in source'),
        ('Retain recovery evidence','Checkpoint rows, state hashes, attempts and a recovery monitor','Implemented in source'),
        ('Demonstrate validation','Python parsing and 12 frontend tests recorded','Tested'),
    ],[1.45,3.85,1.1],8.5)
    caption(doc,'Table','1.1','Project objectives and implementation status')
    ptext(doc,'The scope is a prototype control plane. Nexora is not a public cloud provider, a provider marketplace, a production payment system, a container-orchestration system, or a proven high-availability deployment. The interface contains a resource-pool simulator, while persistent resource-pool policies were not found. Token purchase and card top-up are intentionally simulated. Optional remote streaming depends on separately reachable MediaMTX and destination services and was not verified end to end.')
    add_heading(doc,'1.4 Significance and Boundaries',2)
    ptext(doc,'The principal academic value of Nexora is that it exposes the entire path from user intent to provider-side execution. It shows how authentication, capacity metadata, scheduling, persistence, telemetry, real-time delivery, recovery and accounting interact. The main boundary is important: the control plane coordinates provider-owned machines; it does not itself sell, host or guarantee compute capacity. In particular, a configured render or Vercel deployment is not evidence of a verified operational service.')

    # Chapter 2
    chapter(doc,2,'Literature Review and Core Concepts')
    add_heading(doc,'2.1 Distributed Compute Orchestration',2)
    ptext(doc,'Distributed compute orchestration is the coordination of workloads across separately managed resources. A practical orchestration layer requires a clear distinction between the control plane, which makes policy and stores system state, and the data or execution plane, which performs work on a provider machine. Nexora follows this concept: the FastAPI control plane persists users, providers, jobs and accounting data, whereas the provider agent inspects local hardware and runs the assigned workload. The project is intentionally smaller in scope than mature cluster schedulers, but the separation makes responsibilities explicit.')
    add_heading(doc,'2.2 Control Plane and Provider Agent Architecture',2)
    ptext(doc,'A control plane can expose stable HTTP APIs while agents use periodic heartbeats and polling to function through common firewall and NAT environments. In Nexora, the provider sends a shared-token registration request and periodic heartbeats. It then polls its pending-job endpoint every two seconds. This pull model avoids requiring the control plane to initiate a connection to the provider. The trade-off is dispatch latency and the need for robust job-claim semantics; the current source returns scheduled jobs before the provider asynchronously records RUNNING, which is a documented reliability risk.')
    add_heading(doc,'2.3 Scheduling, Checkpointing and Recovery',2)
    ptext(doc,'Scheduling requires eligibility checks before selection. Nexora filters providers by online state, requested CPU, requested memory, optional GPU availability and FFmpeg capability for media-oriented workloads. From candidates it selects the lowest cost per hour adjusted by reliability. This is a rule-based strategy, not an optimization engine, learning algorithm, resource-pool planner or fair-share scheduler. Checkpoints store a sequence number, attempt number, progress, state version, deterministic hash and payload. On loss of a heartbeat, the recovery monitor may mark the failed provider offline, identify a compatible replacement and create a fenced recovery attempt.')
    add_heading(doc,'2.4 Telemetry and Real-Time Communication',2)
    ptext(doc,'Telemetry is a current-state mechanism in this project. The provider reports CPU, RAM and disk utilization through psutil. It optionally uses nvidia-smi for device-wide GPU compute and memory metrics; a Torch allocator fallback can report only process-local GPU memory. The frontend receives state by REST refresh and by a user-scoped WebSocket topic set. Since no historical telemetry entity was found, the live charts represent accumulated frontend snapshots and current provider state rather than a durable observability time series.')
    add_heading(doc,'2.5 Artifact Processing, Streaming and Token Accounting',2)
    ptext(doc,'Artifact handling is necessary when a job requires input or produces output. Nexora validates and probes user video uploads, records metadata and checksums, lets the assigned provider download job input, and lets a provider upload output. The optional streaming path uses a session model: the backend validates an RTMP/RTMPS destination, allocates an FFmpeg-capable provider, hands MediaMTX session credentials to the correct participants, and bills tokens only after streaming state is reported. The project does not itself operate a payment gateway; its wallet and purchase interactions are a token-accounting demonstration.')
    add_table(doc,['Concept','Nexora adaptation','Boundary'],[
        ('Control plane','FastAPI API, SQLAlchemy state, scheduler, recovery monitor','Single-process coordination'),
        ('Provider agent','Hardware probe, polling, execution and heartbeat','Shared provider credential'),
        ('Checkpoint','Hash-protected state and attempt fencing','Live multi-machine recovery not tested'),
        ('Realtime delivery','Authenticated WebSocket topics plus REST resync','In-memory event hub'),
        ('Streaming','MediaMTX/FFmpeg session workflow','External media host required'),
    ],[1.25,3.45,1.7],8.5)
    caption(doc,'Table','2.1','Core concepts mapped to Nexora')

    # Chapter 3
    chapter(doc,3,'System Architecture and Methodology')
    add_heading(doc,'3.1 Proposed System Architecture',2)
    ptext(doc,'Figure 3.1 depicts the source-backed system context. The browser dashboard communicates with the control plane over authenticated REST and a WebSocket endpoint. The control plane uses SQLAlchemy against default SQLite or configured PostgreSQL. Provider agents communicate only with the control plane through authenticated HTTP polling, while optional MediaMTX handles media ingest/read and calls the backend for per-session authorization. A destination such as a video platform is outside Nexora and is never treated as an integrated or tested Nexora component.')
    add_figure(doc,ASSETS/'fig31_architecture.png','3.1','Overall Nexora system architecture')
    add_heading(doc,'3.2 Module Interoperability and Data Flow',2)
    ptext(doc,"Figure 3.2 shows the normal workload path. After login, the frontend submits a job definition. The backend merges the workload into its requirements, verifies any video input artifact, selects a compatible online provider, estimates and reserves tokens, stores a job in SCHEDULED state and publishes events. The provider's listener receives the scheduled job through its polling request, reports RUNNING, emits checkpoint state through the provider endpoints, and finally reports a completed or failed result. Terminal transitions release the provider and settle reserved tokens when the update path is used.")
    add_figure(doc,ASSETS/'fig32_dataflow.png','3.2','Module interoperability and workload data flow')
    add_heading(doc,'3.3 Implementation Environment',2)
    add_heading(doc,'3.3.1 Required system tools',3)
    bullet(doc,'Python 3 environment for the FastAPI control plane and provider agent.')
    bullet(doc,'A browser capable of ES modules, fetch and WebSocket for the static frontend.')
    bullet(doc,'FFmpeg for artifact probing, video compression and optional live encoding; imageio-ffmpeg is a fallback locator in selected code paths.')
    bullet(doc,'Docker and Docker Compose only for the unverified local backend/PostgreSQL/MediaMTX topology.')
    add_heading(doc,'3.3.2 Environment variables',3)
    add_table(doc,['Variable','Component','Purpose'],[
        ('DATABASE_URL','Backend','SQLite default or PostgreSQL connection selection'),
        ('JWT_SECRET','Backend','JWT signature and derived stream-key encryption material'),
        ('PROVIDER_SHARED_TOKEN','Backend and provider','Current shared HTTP provider credential'),
        ('CORS_ORIGINS / CORS_ORIGIN_REGEX','Backend','Browser origin policy'),
        ('MEDIAMTX_INGEST_URL / MEDIAMTX_PROVIDER_READ_URL','Backend','Media addresses returned to clients/providers'),
        ('UCMP_BACKEND_URL','Provider','Explicit control-plane base URL'),
        ('NEXORA_FFMPEG_PATH / FFMPEG_PATH','Provider','FFmpeg discovery override'),
    ],[2.15,1.2,3.05],8.2)
    caption(doc,'Table','3.1','Selected environment configuration variables')
    add_heading(doc,'3.3.3 Key software packages',3)
    add_table(doc,['Technology','Verified source role','Use category'],[
        ('FastAPI 0.115.6 and Uvicorn 0.34.0','HTTP API, WebSocket endpoint, app lifecycle','Backend'),
        ('SQLAlchemy 2.0.36 and psycopg 3.2.3','ORM and PostgreSQL connectivity','Persistence'),
        ('Pydantic 2.10.3','Request schema validation','Backend'),
        ('PyJWT 2.10.1 and cryptography','JWT sessions and Fernet encryption','Security'),
        ('requests 2.32.3 and psutil 6.1.1','Provider communication and utilization','Provider'),
        ('MediaMTX 1.21.2 and FFmpeg','Optional ingest/read/transcode workflow','Streaming'),
    ],[2.1,3.1,1.2],8.2)
    caption(doc,'Table','3.2','Technology stack and actual roles')
    add_heading(doc,'3.3.4 Runtime considerations',3)
    ptext(doc,'The backend defaults to a local SQLite file and creates database tables at application lifespan startup. Docker Compose instead configures PostgreSQL and MediaMTX. The provider agent uses a five-second default heartbeat and a two-second listener polling cadence. The recovery monitor evaluates provider heartbeat age every five seconds and uses a default twenty-second timeout. These timings are implementation defaults, not measured performance guarantees.')
    add_heading(doc,'3.3.5 Logging and artifact locations',3)
    ptext(doc,'The code records audit events in the database and prints selected provider/recovery status messages to process output. Artifacts are stored under the backend application data directory, specifically a `data/artifacts` tree derived from the backend path. No centralized logging, retention worker, object storage integration or historical telemetry table was found. The local filesystem arrangement is suitable for a prototype but constrains durability and scale.')

    # Chapter 4
    chapter(doc,4,'Implementation and Details')
    add_heading(doc,'4.1 Orchestration and Entry Points',2)
    ptext(doc,'The backend entry point is `user-website/backend/app/main.py`, which defines models, request schemas, lifecycle behavior, REST routes and the realtime hub in a single module. The provider entry point is `provider-server/main.py`, which initializes provider identity, hardware information and background heartbeat/listener behavior. The frontend entry point is `user-website/nexora-frontend/index.html`; `js/app.js` initializes routing, state refresh, polling and realtime behavior. The repository contains start scripts for backend, provider and static frontend serving, alongside Docker/Render/Vercel configuration.')
    code_block(doc, '''# Backend scheduling decision - simplified source-backed excerpt
for p in s.query(Provider).all():
    if p.id == exclude_id or p.status not in ("ONLINE", "AVAILABLE"):
        continue
    if p.cpu_cores < min_cores or p.ram_gb < min_ram:
        continue
    if requirements.get("gpu_required") and not p.gpu_name:
        continue
    candidates.append(p)
return min(candidates, key=lambda x: x.cost_per_hour / (max(x.reliability, 1) / 100))''')
    caption(doc,'Listing','4.1','Condensed provider eligibility and selection logic based on `compatible_provider`')
    add_heading(doc,'4.2 Authentication and Session Management',2)
    ptext(doc,'Registration and login accept an email and a minimum eight-character password. Password hashes use PBKDF2-HMAC-SHA256 with a generated salt and 600,000 rounds. A successful session creates an `auth_sessions` record and a JWT containing a user subject, session identifier, email and expiry. The `current_user` dependency verifies the JWT and checks that the associated database session exists, is not revoked and has not expired. Browser WebSocket authentication uses a `nexora.jwt.<token>` WebSocket subprotocol instead of placing the bearer token in the URL.')
    ptext(doc,'The implementation does not expose an observed logout/revoke endpoint, password reset flow, administrator role, or role-based authorization layer. User-facing resources generally filter jobs/artifacts by owning user, whereas provider endpoints are protected by one configured shared token. This distinction is material to the security analysis in Chapter 5.')
    add_heading(doc,'4.3 Provider Registration and Telemetry',2)
    ptext(doc,'The provider maintains a persistent locally generated provider ID unless overridden by environment. At registration, it sends logical CPU core count, RAM size, optional GPU name and memory, configured cost per hour, detailed system information, FFmpeg availability and detected H.264 encoder names. Heartbeats store current provider status and utilization. CPU, RAM and disk values use psutil; `nvidia-smi` may produce device-wide GPU compute/memory utilization. The backend serializes provider state and emits provider/telemetry events to realtime subscribers.')
    ptext(doc,'Provider authentication compares the received `X-Provider-Token` against a single configured secret. The provider ID remains supplied in the route/body rather than being cryptographically bound to an enrolled identity. The report labels this design as implemented but unsuitable as a strong production identity model.')
    add_heading(doc,'4.4 Workload Submission and Scheduling',2)
    ptext(doc,'A user POSTs a `JobCreate` body containing a bounded name, workload string and requirements object. The backend creates a provider-compatible requirements dictionary, validates a referenced artifact for video compression, chooses a provider, estimates tokens, ensures wallet balance, marks the provider BUSY, persists the job and creates a reservation ledger entry plus job billing row. For submitted Python source, it stores a source artifact record. The provider listener polls for jobs assigned to its own ID and creates a thread per returned job. This is a functional prototype mechanism, but the absence of an atomic execution claim creates a possible duplicate-dispatch race.')
    add_figure(doc,ASSETS/'fig33_lifecycle.png','4.1','Implemented workload lifecycle and recovery state concepts')
    add_heading(doc,'4.5 Provider Execution and Job Lifecycle',2)
    ptext(doc,'Provider execution supports matrix multiplication, prime search, Fibonacci, video compression and custom Python branches. Controlled computation functions report progress and state to the checkpoint helper. Custom Python writes supplied source into a temporary directory and invokes the isolated Python interpreter mode using `-I`; however, isolated interpreter mode does not form a security sandbox. In a trusted demonstration environment the feature shows flexible dispatch. In an untrusted environment it is a high-risk remote-code-execution path and requires container or VM isolation, resource quotas and network/file restrictions.')
    add_heading(doc,'4.6 Checkpointing and Failure Recovery',2)
    ptext(doc,'A checkpoint contains job/provider identifiers, attempt and sequence values, progress, state version, canonical state hash and payload. Provider updates carry an attempt value; stale updates are rejected by a fencing check. A background recovery thread identifies providers whose heartbeat exceeds the configured timeout. It marks a lost provider OFFLINE, finds the latest checkpoint for affected jobs, selects a replacement provider where possible, increments the attempt and recovery count, marks the job RECOVERING and embeds resume metadata in requirements. If no replacement exists, it marks the job failed and refunds the outstanding reservation. Figure 4.2 summarizes this control path.')
    add_figure(doc,ASSETS/'fig34_recovery.png','4.2','Checkpoint recovery and provider-loss handling workflow')
    add_heading(doc,'4.7 Frontend State Management and Realtime Events',2)
    ptext(doc,'The static frontend uses ES modules rather than React. `router.js` maps landing, overview, jobs, streaming, providers, resource-pool, billing, analytics and settings views. Console routes require local authenticated state. `api.js` stores a selected API base and bearer token, wraps fetch errors and supports artifact upload. `state.js` obtains dashboard, jobs, providers, checkpoints, billing, analytics and active-stream data through a coordinated refresh. `realtime.js` subscribes to allowed topics, sends pings, reconnects with backoff and requests REST resynchronization after connection changes or recovery events.')
    add_heading(doc,'4.8 Artifact Processing and Video Workloads',2)
    ptext(doc,'The input artifact endpoint accepts selected video extensions and MIME types, streams uploads to a generated artifact directory, enforces a configured maximum size, probes the file through FFmpeg, rejects invalid or oversized-duration videos, calculates a SHA-256 checksum, and persists metadata. An owner can retrieve artifact metadata or download output tied to an owned job. The provider has a dedicated download route for job input and an upload route for output. The provider output upload path does not apply the same observed size/type/duration validation as the user input path, so this is a current technical debt item.')
    add_heading(doc,'4.9 Token Wallet and Billing',2)
    ptext(doc,'Wallets are created on demand with an initial token adjustment. A token ledger records the balance before and after each server-side mutation. Job estimation uses workload requirements and provider-related information to reserve tokens before dispatch. On terminal provider update, the current code settles a reservation only while the reservation remains positive: it refunds the full reservation and then debits calculated actual usage for successful work. Stream usage is billed only after the provider reports STREAMING and a complete minute has elapsed. Payment-related UI and top-up API flows are simulated; no payment gateway, charge authorization or external transaction confirmation is implemented.')
    add_heading(doc,'4.10 Remote Live Stream Encoding',2)
    ptext(doc,'Streaming sessions add a specialized but optional workflow. The backend validates destination platform, profile, token balance, URL host/scheme and provider FFmpeg capability. It creates session-scoped publish/read credentials and encrypts the destination key with Fernet derived from the configured JWT secret. MediaMTX sends publish/read authorization requests to an internal backend callback. The assigned provider claims exactly one session through the provider API, receives a source URL and destination credentials, starts FFmpeg and sends stream heartbeat metrics. Stream stop may be immediate before claim or asynchronous after a STOPPING command. Figure 4.3 depicts this source-backed topology; it must not be treated as a demonstrated public broadcast.')
    add_figure(doc,ASSETS/'fig37_stream.png','4.3','Optional MediaMTX and FFmpeg remote streaming architecture')

    # Chapter 5
    chapter(doc,5,'Results and Analysis')
    add_heading(doc,'5.1 Qualitative Results and Implementation Artifacts',2)
    ptext(doc,'The strongest result available for this report is implementation evidence, not a performance benchmark. Repository inspection confirms a coherent control-plane/provider path: user routes, provider routes, data models, scheduling logic, background recovery logic, frontend pages, stream configuration and test files are present. The frontend includes views for overview, jobs, providers, resource-pool simulation, billing, analytics, settings and streaming. The backend includes routes for those user workflows and provider-facing polling/update operations. Figure 5.1 presents the data relationships that make the workflow durable at application level.')
    add_figure(doc,ASSETS/'fig35_er.png','5.1','Entity relationship view derived from SQLAlchemy model declarations')
    add_heading(doc,'5.2 Quantitative Validation Evidence',2)
    ptext(doc,'The audit recorded only the checks that were actually executed. Both primary Python modules compiled successfully with `py_compile`. The Node test runner executed twelve frontend utility tests across browser capture and stream stopping with zero failures. These tests covered error reporting, WHIP negotiation/cleanup behavior, capture cleanup, backend stop confirmation and idempotent combined cleanup. They do not demonstrate a native capture session, a media server or a remote destination broadcast.')
    add_table(doc,['Validation activity','Result','Interpretation'],[
        ('Python syntax compilation: backend and provider modules','Passed, exit code 0','Modules parsed; runtime behavior not established'),
        ('Node utility tests for browser capture and stream stop','Passed: 12 tests, 0 failures','Focused unit behavior; external media mocked/absent'),
        ('Backend pytest suite','Not run','pytest absent from supplied virtual environment'),
        ('Provider pytest suite','Not run','pytest absent from supplied virtual environment'),
        ('Docker Compose, database, MediaMTX, OBS, cloud deployment','Not run','End-to-end behavior unverified'),
    ],[2.45,1.25,2.8],8.5)
    caption(doc,'Table','5.1','Validation evidence actually available to this report')
    add_heading(doc,'5.3 Feature Implementation and Verification Matrix',2)
    add_table(doc,['Capability','Implementation status','Validation status','Evidence boundary'],[
        ('JWT session and user routes','Implemented in source','Unverified runtime','Models and auth routes present'),
        ('Provider registration and heartbeat','Implemented in source','Unverified live provider','Provider/client routes present'),
        ('Capacity/cost selection','Implemented in source','Unverified integrated','Rule-based scheduler in backend'),
        ('Checkpoint and recovery','Implemented in source','Unverified multi-machine','Recovery monitor and tests inspected'),
        ('Token accounting','Implemented in source','Unverified functional','Ledger/reservation/settlement code'),
        ('Resource-pool interface','Simulated','N/A','Client-side candidate filtering'),
        ('Payment purchase','Simulated','N/A','Configured demo packages only'),
        ('Media streaming','Implemented in source','Unverified end to end','Routes, MediaMTX config, provider runner'),
    ],[1.6,1.6,1.4,2.0],7.7)
    caption(doc,'Table','5.2','Feature status matrix with explicit verification boundaries')
    add_heading(doc,'5.4 Edge Cases and Limitations',2)
    bullet(doc,'Historical telemetry persistence was not found. Dashboard utilization derives from current provider state and frontend snapshots.')
    bullet(doc,'Administrator RBAC was not found; authenticated users can list providers through the observed API.')
    bullet(doc,'Cancellation state is recorded but does not show an observed command path that terminates a running provider workload; stop-all does not show reservation refunds.')
    bullet(doc,'Artifact output upload lacks the same observed content limits applied to user input artifact upload.')
    bullet(doc,'Media deployment requires a separately reachable MediaMTX host with applicable TCP/UDP, TLS and NAT configuration; Render web service configuration alone is insufficient.')
    add_heading(doc,'5.5 Security and Reliability Analysis',2)
    add_table(doc,['Risk','Evidence','Impact','Recommended mitigation'],[
        ('Custom Python execution','Provider writes/runs submitted source','Untrusted code can affect provider host','Container/VM isolation, quotas, network/file policy'),
        ('Shared provider token','Single configured provider credential','Provider impersonation if secret leaks','Per-provider enrollment, rotation or mTLS'),
        ('Dispatch race','Polling returns jobs before asynchronous RUNNING update','Possible duplicate local execution','Atomic lease/claim and single-slot worker control'),
        ('Single-process coordination','In-memory event hub/recovery plus SQLite default','Replica/durability limits','PostgreSQL baseline, queue/lock/pubsub'),
        ('Local artifact storage','Backend filesystem artifact paths','Durability and exhaustion risk','Object store, retention and output limits'),
    ],[1.35,1.65,1.65,2.0],7.6)
    caption(doc,'Table','5.3','Security and reliability findings')
    add_heading(doc,'5.6 Deployment Topology',2)
    ptext(doc,'Figure 5.2 presents the available deployment configurations. Direct local operation uses separate backend, provider and static-server processes. Docker Compose defines backend, PostgreSQL and MediaMTX services but does not start a provider. The Render and Vercel files define a potential hosted backend/database and static frontend topology. An external media host remains required for remote streaming. The audit did not deploy any of these configurations.')
    add_figure(doc,ASSETS/'fig36_deploy.png','5.2','Documented but unverified deployment topology')

    # Chapter 6
    chapter(doc,6,'Conclusion and Future Work')
    add_heading(doc,'6.1 Conclusion',2)
    ptext(doc,'Nexora demonstrates a complete source-level prototype of a unified compute management workflow. The project connects user-facing job submission to provider discovery, capacity filtering, selection, polling-based dispatch, provider execution, checkpoints, recovery state, artifacts, token ledger operations and dashboard updates. Its design is particularly useful as an academic case study because each concern remains visible in a compact repository: the frontend is static and inspectable, the backend exposes the state model and routes, and the provider agent reveals the boundary between control-plane decisions and local execution.')
    ptext(doc,'The implementation should nevertheless be described accurately. Python syntax validation and twelve frontend utility tests are the runtime evidence recorded in this report. The principal integrations - actual provider execution, database deployment, Docker Compose, MediaMTX, OBS/browser capture, remote streaming, external destination delivery and hosted service deployment - remain unverified. Nexora is therefore a substantial prototype, not a production readiness claim.')
    add_heading(doc,'6.2 Future Enhancements',2)
    add_table(doc,['Priority','Future work','Acceptance criterion'],[
        ('P0','Isolate custom code and strengthen provider identity','Untrusted workload cannot access provider host; one credential cannot impersonate another provider'),
        ('P1','Add atomic leases, cancellation acknowledgements and recovery stress tests','One job has one active execution; cancel reaches the provider and settles once'),
        ('P1','Use durable production persistence and artifact management','Versioned migrations, retained backups, object storage lifecycle and limits'),
        ('P2','Add telemetry history, structured logs, health alerts and audit visibility','Operators can inspect time-series and correlated job/provider events'),
        ('P2','Refresh docs and run CI/integration suites','Documented routes/config align with source and automated tests run reproducibly'),
        ('P3','Formalize roles, quotas, provider pools and fair scheduling','Policy-backed access and predictable multi-provider allocation'),
    ],[0.6,3.1,2.9],8.2)
    caption(doc,'Table','6.1','Prioritized future-work roadmap')

    # Supporting materials, references, appendices
    pb(doc)
    add_heading(doc,'SUPPORTING MATERIALS',1)
    ptext(doc,'The following source materials were inspected to prepare this report: `README.md`; the backend control plane at `user-website/backend/app/main.py`; the provider agent at `provider-server/main.py`; static frontend modules under `user-website/nexora-frontend/js`; Docker and hosting configuration; MediaMTX configuration; backend/provider/frontend tests; and the supplied audit documents `OVERALL_PROJECT_REPORT.md`, `API_REFERENCE.md`, `ARCHITECTURE.md`, `DATABASE_DESIGN.md`, `DEPLOYMENT_GUIDE.md`, `FEATURE_IMPLEMENTATION_MATRIX.md`, `TESTING_AND_VALIDATION.md`, and `TECHNICAL_DEBT_AND_FUTURE_SCOPE.md`. The reference PBC format document was used for chapter sequence, cover composition, abstract, table of contents, heading structure, supporting materials, references and appendix arrangement.')
    add_heading(doc,'REFERENCES',2)
    refs=[
        '[1] Nexora repository, README.md, backend, provider, frontend, tests and deployment configuration. Inspected 25-26 October 2026.',
        '[2] Nexora Overall Project Report, API Reference, Architecture, Database Design, Deployment Guide, Feature Implementation Matrix, Testing and Validation, and Technical Debt and Future Scope. Internal project documentation, 2026.',
        '[3] FastAPI. FastAPI Documentation. https://fastapi.tiangolo.com/ (accessed for framework context; project-specific facts are based on source code).',
        '[4] SQLAlchemy. SQLAlchemy 2.0 Documentation. https://docs.sqlalchemy.org/en/20/.',
        '[5] Docker. Docker Compose Documentation. https://docs.docker.com/compose/.',
        '[6] MediaMTX. MediaMTX Documentation. https://mediamtx.org/docs/.',
        '[7] FFmpeg. FFmpeg Documentation. https://ffmpeg.org/documentation.html.',
        '[8] Python Software Foundation. Python 3 Documentation. https://docs.python.org/3/.',
    ]
    for x in refs: ptext(doc,x,align=WD_ALIGN_PARAGRAPH.LEFT,size=11,after=4)

    pb(doc)
    add_heading(doc,'APPENDIX',2)
    add_heading(doc,'Appendix A: API and Database Design Summary',3)
    ptext(doc,'This appendix preserves the reference report position for extended technical material while adapting it to Nexora. It is a compact companion to the full API_REFERENCE.md and DATABASE_DESIGN.md documents.')
    add_heading(doc,'A.1 API Endpoint Groups',3)
    add_table(doc,['Group','Representative endpoints','Authentication'],[
        ('Health and authentication','GET /health; POST /auth/register; POST /auth/login','Public'),
        ('User/job workflow','GET/POST /jobs; cancel; checkpoints; dashboard; analytics','Bearer JWT'),
        ('Billing and artifacts','billing, transactions, purchase, demo top-up, upload/download','Bearer JWT'),
        ('Provider workflow','register, heartbeat, pending jobs, updates, checkpoints, artifacts','X-Provider-Token'),
        ('Streaming','stream sessions, MediaMTX callback, claim, heartbeat, stopped','JWT, provider token or callback'),
        ('Realtime','WS /ws/realtime','JWT in WebSocket subprotocol'),
    ],[1.5,3.8,1.3],8.4)
    caption(doc,'Table','A.1','API endpoint groups')
    add_heading(doc,'A.2 Database Entities and Relationships',3)
    ptext(doc,'Core entities are users, providers, jobs, checkpoints, auth sessions, job artifacts, wallets, token transactions, job billing, audit events and stream sessions. Users own sessions, wallet records, jobs and artifacts. Jobs reference users and an optional provider, own checkpoints/artifacts and have one billing record. Stream sessions reference users and optional providers. The following figure repeats the relationship summary for appendix use.')
    add_figure(doc,ASSETS/'fig35_er.png','A.1','Database entity relationship summary')
    add_heading(doc,'A.3 Selected Source Listings',3)
    code_block(doc,'''# Source-backed heartbeat update behavior
@app.post("/providers/{provider_id}/heartbeat")
def heartbeat(provider_id: str, body: Heartbeat, _=Depends(provider_auth), s: Session=Depends(db)):
    p = s.get(Provider, provider_id)
    if not p:
        raise HTTPException(404, "Provider not registered")
    p.status = body.status
    p.utilization = body.utilization
    p.last_heartbeat = datetime.now(timezone.utc)
    s.commit()
    return {"ok": True}''')
    caption(doc,'Listing','A.1','Condensed provider heartbeat endpoint behavior')

    pb(doc)
    add_heading(doc,'Appendix B: Deployment, Testing and Implementation Checklist',3)
    add_heading(doc,'B.1 Direct Local Setup',3)
    ptext(doc,'Repository-supported local setup separates backend, provider and static frontend. The backend can run Uvicorn for `app.main:app`; the provider uses `python main.py`; and the frontend can be served with Python HTTP server or its provided batch script. The provider must use the same control-plane URL and provider shared token as the backend. These are documented commands, not commands executed by this audit.')
    code_block(doc,'''# Repository-supported example commands (not executed for this report)
cd user-website/backend
uvicorn app.main:app --host 0.0.0.0 --port 8000

cd provider-server
python main.py

cd user-website/nexora-frontend
python -m http.server 5173 --bind 127.0.0.1''')
    caption(doc,'Listing','B.1','Repository-supported local startup commands')
    add_heading(doc,'B.2 Docker and Hosted Setup',3)
    ptext(doc,'The root Docker Compose file describes a backend, PostgreSQL and MediaMTX topology. `render.yaml` defines a Render web service and PostgreSQL database; `vercel.json` serves the static frontend. An internet-accessible media deployment requires a host that exposes the required RTMP, RTSP and WebRTC ports. The deployment guide also records that a standard Render web service is not that media host.')
    add_heading(doc,'B.3 Test and Evidence Checklist',3)
    add_table(doc,['Item','Recorded outcome','Report classification'],[
        ('Python primary-module parse check','Passed','Tested'),
        ('Frontend browser-capture/stream-stop utilities','12 passed, 0 failed','Tested'),
        ('Backend and provider pytest suites','pytest missing; not run','Unverified'),
        ('Control-plane APIs with live database','Not run','Unverified'),
        ('Docker/PostgreSQL/MediaMTX','Not run','Unverified'),
        ('Remote provider and destination stream','Not run','Unverified'),
    ],[2.6,2.0,2.0],8.5)
    caption(doc,'Table','B.1','Testing and validation checklist')
    add_heading(doc,'B.4 Final Audit Notes',3)
    ptext(doc,'No secret values are reproduced in this report. Implementation claims are linked to repository evidence, and claims of successful live deployment, payment processing, remote execution, external media delivery, performance or scalability are intentionally excluded unless the supplied audit recorded a corresponding executed check. The report uses placeholders for student-specific information because no student names or registration numbers were provided.')

    doc.save(DOCX_OUT)

    validation = '''# Nexora PBC Report Validation\n\n## Deliverables\n\n- `Nexora_PBC_Project_Report.docx`: complete editable academic report generated in the reference structure.\n\n## Reference format mapped\n\n- Cover page with institution, degree, student placeholders and template guide name.\n- Abstract and table of contents placement.\n- Six-chapter sequence: Introduction; Literature Review and Core Concepts; System Architecture and Methodology; Implementation and Details; Results and Analysis; Conclusion and Future Work.\n- Supporting Materials, References and two appendices.\n- US Letter page with 1-inch margins, Times New Roman body typography, centered cover elements, page footer fields, Word tables, captions and chapter page breaks.\n\n## Evidence used\n\n- Nexora source repository: backend, provider, frontend, configuration, tests and documentation.\n- Supplied audit documents: API reference, architecture, database design, deployment guide, feature matrix, overall project report, technical debt/future scope, testing/validation.\n- PBC Report Format.docx for the authoritative heading sequence and visual conventions.\n\n## Figures and tables generated\n\n- 7 diagrams: system architecture, data flow, workload lifecycle, recovery workflow, entity relationships, deployment topology and streaming flow.\n- 10 numbered tables plus appendix tables and selected code listings.\n\n## Checks performed\n\n- Re-opened the generated document with python-docx after save (performed by validation command).\n- Verified the report uses required chapter titles and produces a non-empty DOCX file.\n- Checked that report text contains no configured secret values.\n- Prior project validation evidence preserved accurately: Python syntax parse passed; Node frontend utilities passed 12/12; pytest and end-to-end integrations not run.\n\n## Known limitations\n\n- The bundled DOCX renderer could not render because LibreOffice `soffice.exe` was unavailable on the tool PATH. As a result, PDF conversion and page-by-page raster visual inspection were not performed by the automation.\n- Word TOC page references may need field refresh in Microsoft Word (Ctrl+A, F9) after opening the document. The structural table of contents is present.\n- Student identity fields remain intentional placeholders.\n- No live deployment, database, provider, MediaMTX, OBS/browser-capture or destination streaming workflow is claimed as verified.\n'''
    VALIDATION_OUT.write_text(validation, encoding='utf-8')

if __name__ == '__main__':
    build()
