from pathlib import Path
from copy import deepcopy
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(r"C:\Users\KALYAN PAGADALA\Desktop\Nexora-Unified-Compute-Management-Platform-")
OUT = ROOT / "Nexora_PBC_Report"
BASE = OUT / "Nexora_PBC_Project_Report.docx"
FINAL = OUT / "Nexora_PBC_Project_Report_Final.docx"
ASSETS = OUT / "final_assets"
ASSETS.mkdir(exist_ok=True)

BLACK = "000000"; NAVY = "163A5F"; BLUE = "2E75B6"; PALE = "D9EAF7"; GREEN = "D9EAD3"; ORANGE = "FCE4D6"; YELLOW = "FFF2CC"

def font(run, size=11, bold=False, italic=False, color=BLACK, face='Times New Roman'):
    run.font.name = face
    run._element.rPr.rFonts.set(qn('w:ascii'), face)
    run._element.rPr.rFonts.set(qn('w:hAnsi'), face)
    run.font.size = Pt(size); run.bold = bold; run.italic = italic
    run.font.color.rgb = RGBColor.from_string(color)

def shade(cell, color):
    tcPr = cell._tc.get_or_add_tcPr(); node = OxmlElement('w:shd'); node.set(qn('w:fill'), color); tcPr.append(node)

def cell_text(cell, value, bold=False, size=8.2, color=BLACK):
    cell.text = ''
    p = cell.paragraphs[0]; p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.space_after = Pt(0); p.paragraph_format.line_spacing = 1.08
    r = p.add_run(str(value)); font(r, size, bold, False, color)
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    tcPr = cell._tc.get_or_add_tcPr(); mar = tcPr.first_child_found_in('w:tcMar')
    if mar is None: mar = OxmlElement('w:tcMar'); tcPr.append(mar)
    for tag in ['top','start','bottom','end']:
        el = mar.find(qn('w:'+tag))
        if el is None: el = OxmlElement('w:'+tag); mar.append(el)
        el.set(qn('w:w'),'100'); el.set(qn('w:type'),'dxa')

def table_header(row):
    pr = row._tr.get_or_add_trPr(); e = OxmlElement('w:tblHeader'); e.set(qn('w:val'),'true'); pr.append(e)

def move_after(block, anchor):
    element = block._element
    element.getparent().remove(element)
    anchor_element = anchor._p if hasattr(anchor, '_p') else anchor._tbl
    anchor_element.addnext(element)
    return block

def para_after(doc, anchor, text='', heading=None, bold=False, italic=False, size=11.5, align=WD_ALIGN_PARAGRAPH.JUSTIFY, before=0, after=6):
    p = doc.add_paragraph(style=f'Heading {heading}' if heading else None)
    p.alignment = align
    p.paragraph_format.space_before = Pt(before)
    p.paragraph_format.space_after = Pt(after)
    p.paragraph_format.line_spacing = 1.4 if not heading else 1.0
    p.paragraph_format.keep_with_next = bool(heading)
    r=p.add_run(text); font(r, 15 if heading==1 else (13 if heading==2 else (12 if heading==3 else size)), True if heading else bold, italic, BLACK)
    return move_after(p,anchor)

def table_after(doc, anchor, headers, rows, widths=None, size=7.8):
    t = doc.add_table(rows=1, cols=len(headers)); t.style='Table Grid'; t.alignment=WD_TABLE_ALIGNMENT.CENTER
    table_header(t.rows[0])
    for i,h in enumerate(headers): cell_text(t.rows[0].cells[i],h,True,size,'FFFFFF'); shade(t.rows[0].cells[i],NAVY)
    for ri,row in enumerate(rows):
        cells=t.add_row().cells
        for i,value in enumerate(row):
            cell_text(cells[i],value,False,size)
            if ri%2==1: shade(cells[i],'F7FAFC')
    if widths:
        for row in t.rows:
            for i,w in enumerate(widths): row.cells[i].width=Inches(w)
    return move_after(t,anchor)

def caption_after(doc, anchor, label, text):
    p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER; p.paragraph_format.space_before=Pt(2); p.paragraph_format.space_after=Pt(8)
    r=p.add_run(f'{label}: {text}'); font(r,10,True,True)
    return move_after(p,anchor)

def image_after(doc, anchor, path, width=6.25):
    p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER; p.paragraph_format.space_before=Pt(4); p.paragraph_format.space_after=Pt(2)
    p.add_run().add_picture(str(path),width=Inches(width))
    return move_after(p,anchor)

def code_after(doc, anchor, code):
    p=doc.add_paragraph(); p.paragraph_format.left_indent=Inches(.25); p.paragraph_format.right_indent=Inches(.25); p.paragraph_format.line_spacing=1.0; p.paragraph_format.space_after=Pt(6)
    shd=OxmlElement('w:shd'); shd.set(qn('w:fill'),'F2F2F2'); p._p.get_or_add_pPr().append(shd)
    for line in code.strip().splitlines():
        r=p.add_run(line+'\n'); font(r,8.3,False,False,BLACK,'Consolas')
    return move_after(p,anchor)

def diagram(path, title, nodes, edges, width=1800, height=1050):
    im=Image.new('RGB',(width,height),'white'); d=ImageDraw.Draw(im)
    try:
        title_font=ImageFont.truetype('arialbd.ttf',42); text_font=ImageFont.truetype('arial.ttf',25); small=ImageFont.truetype('arial.ttf',20)
    except OSError:
        title_font=text_font=small=ImageFont.load_default()
    d.text((width//2,35),title,fill='#000000',font=title_font,anchor='ma')
    fills={'blue':'#D9EAF7','green':'#D9EAD3','orange':'#FCE4D6','yellow':'#FFF2CC','gray':'#F2F2F2'}
    for key,(x,y,w,h,label,kind) in nodes.items():
        d.rounded_rectangle((x,y,x+w,y+h),radius=18,fill=fills[kind],outline='#163A5F',width=3)
        words=label.split(); lines=[]; line=''
        for word in words:
            test=(line+' '+word).strip()
            if d.textbbox((0,0),test,font=text_font)[2] > w-26 and line: lines.append(line); line=word
            else: line=test
        if line: lines.append(line)
        y0=y+h/2-(len(lines)*15)
        for line in lines:
            d.text((x+w/2,y0),line,fill='#111111',font=text_font,anchor='ma'); y0+=31
    for a,b,label in edges:
        ax,ay,aw,ah,_,_=nodes[a]; bx,by,bw,bh,_,_=nodes[b]
        sx=ax+aw/2; sy=ay+ah/2; ex=bx+bw/2; ey=by+bh/2
        if abs(ex-sx)>abs(ey-sy):
            sx=ax+aw if ex>sx else ax; ex=bx if ex>sx else bx+bw
        else:
            sy=ay+ah if ey>sy else ay; ey=by if ey>sy else by+bh
        d.line((sx,sy,ex,ey),fill='#2E75B6',width=5)
        if abs(ex-sx)>abs(ey-sy):
            arrow=[(ex,ey),(ex-18 if ex>sx else ex+18,ey-10),(ex-18 if ex>sx else ex+18,ey+10)]
        else:
            arrow=[(ex,ey),(ex-10,ey-18 if ey>sy else ey+18),(ex+10,ey-18 if ey>sy else ey+18)]
        d.polygon(arrow,fill='#2E75B6')
        if label:
            mx,my=(sx+ex)/2,(sy+ey)/2
            d.rectangle((mx-74,my-17,mx+74,my+17),fill='white')
            d.text((mx,my),label,fill='#163A5F',font=small,anchor='mm')
    im.save(path)

def make_diagrams():
    diagrams={}
    diagrams['architecture']=(
        {'u':(70,240,250,100,'Authenticated User','blue'),'f':(410,240,270,100,'Static JavaScript Frontend','blue'),'api':(790,210,300,150,'FastAPI Control Plane API Scheduler Realtime Hub','green'),'db':(1210,240,240,100,'SQLite Default or PostgreSQL','yellow'),'p':(790,520,300,110,'Provider Agent Hardware Probe Workloads','orange'),'m':(1210,520,240,110,'MediaMTX Optional','yellow'),'d':(1510,520,220,110,'External Stream Destination','gray')},
        [('u','f','HTTPS'),('f','api','REST JWT'),('api','db','SQLAlchemy'),('p','api','Polling Heartbeat'),('m','api','Auth callback'),('p','m','RTSP RTMP'),('m','d','RTMP S')])
    diagrams['auth']=(
        {'form':(60,300,230,100,'Login or Registration Form','blue'),'auth':(390,300,240,100,'Auth Route Validation','green'),'hash':(720,160,240,100,'PBKDF2 SHA256 Password Hash','yellow'),'session':(720,430,240,100,'Auth Session Record','yellow'),'jwt':(1070,300,240,100,'JWT with User and Session ID','orange'),'guard':(1410,300,250,100,'Route and WebSocket Access Check','blue')},
        [('form','auth','POST'),('auth','hash','register'),('auth','session','create'),('session','jwt','issue'),('jwt','guard','Bearer or protocol')])
    diagrams['heartbeat']=(
        {'probe':(60,250,260,105,'Provider psutil nvidia smi FFmpeg Probe','orange'),'reg':(430,250,240,105,'Provider Registration','blue'),'record':(780,250,250,105,'Provider Record Capacity State','green'),'beat':(430,520,240,105,'Heartbeat Every 5 Seconds Default','blue'),'tele':(780,520,250,105,'Utilization and Timestamp','green'),'ui':(1160,385,260,105,'Dashboard REST and WebSocket Updates','yellow')},
        [('probe','reg','metadata'),('reg','record','token'),('beat','tele','utilization'),('record','ui','provider event'),('tele','ui','telemetry event'),('record','beat','provider id')])
    diagrams['schedule']=(
        {'job':(50,390,210,95,'Job Request and Requirements','blue'),'filter':(350,240,280,130,'Filter Online Capacity GPU FFmpeg','green'),'score':(760,240,280,130,'Cost divided by Reliability Score','yellow'),'reserve':(1160,240,240,130,'Reserve Wallet Tokens','orange'),'persist':(1510,240,220,130,'Persist SCHEDULED Job','blue'),'pending':(1510,530,220,100,'Provider Polls Pending Job','green'),'run':(1160,530,240,100,'RUNNING Updates Checkpoints Result','orange'),'settle':(760,530,280,100,'Settle Reservation and Release Provider','yellow')},
        [('job','filter','requirements'),('filter','score','eligible'),('score','reserve','winner'),('reserve','persist','balance'),('persist','pending','poll'),('pending','run','payload'),('run','settle','terminal')])
    diagrams['recovery']=(
        {'mon':(50,280,235,105,'Five Second Recovery Monitor','blue'),'timeout':(390,280,235,105,'Heartbeat Timeout Detection','orange'),'off':(730,280,220,105,'Mark Provider Offline','yellow'),'cp':(1060,140,250,105,'Load Latest Checkpoint','green'),'find':(1060,430,250,105,'Find Replacement Provider','green'),'rec':(1420,140,260,105,'RECOVERING New Attempt Fencing','blue'),'fail':(1420,430,260,105,'FAILED and Refund Reservation','orange')},
        [('mon','timeout','age'),('timeout','off','expired'),('off','cp','affected jobs'),('off','find','compatibility'),('cp','rec','state'),('find','rec','exists'),('find','fail','none')])
    diagrams['wallet']=(
        {'create':(70,300,230,100,'Wallet Initial Token Adjustment','blue'),'purchase':(400,150,230,100,'Configured Package Purchase Simulation','yellow'),'job':(400,440,230,100,'Job Estimate and Reservation','orange'),'ledger':(780,300,260,100,'Token Transaction Ledger Before After','green'),'terminal':(1160,300,240,100,'Completion Failure or Cancel','blue'),'refund':(1480,150,230,100,'Refund or Settlement','yellow'),'usage':(1480,440,230,100,'Debit Actual Job or Stream Usage','orange')},
        [('create','ledger','credit'),('purchase','ledger','credit'),('job','ledger','reserve'),('ledger','terminal','state'),('terminal','refund','return'),('terminal','usage','usage')])
    diagrams['artifact']=(
        {'upload':(60,300,230,100,'User Multipart Upload','blue'),'valid':(400,300,240,100,'Extension MIME Size FFmpeg Probe','green'),'store':(760,300,230,100,'Artifact File and Metadata Checksum','yellow'),'job':(1120,160,240,100,'Attach Input Artifact to Job','orange'),'download':(1120,450,240,100,'Provider Download by Job Artifact','blue'),'out':(1480,300,230,100,'Provider Output Upload and Owner Download','green')},
        [('upload','valid','stream'),('valid','store','valid'),('store','job','id'),('job','download','assigned'),('download','out','processed')])
    diagrams['stream']=(
        {'session':(60,360,240,100,'Create Stream Session','blue'),'select':(400,360,240,100,'Select Encoder Capable Provider','green'),'keys':(750,360,240,100,'Session Publish Read and Destination Credentials','yellow'),'media':(1100,180,260,110,'MediaMTX RTMP WHIP RTSP','orange'),'agent':(1100,540,260,110,'Provider FFmpeg Encoder','orange'),'dest':(1490,360,240,100,'YouTube Twitch Custom RTMP','gray')},
        [('session','select','profile'),('select','keys','allocate'),('keys','media','publish read'),('media','agent','RTSP'),('agent','dest','RTMP'),('media','session','auth callback'),('agent','session','heartbeat billing')])
    diagrams['deploy']=(
        {'browser':(60,340,230,100,'Browser at Static Frontend','blue'),'vercel':(390,160,230,100,'Vercel Static Hosting Optional','yellow'),'api':(390,520,230,100,'Local or Render Control Plane','green'),'db':(750,520,220,100,'SQLite or Render PostgreSQL','yellow'),'provider':(1110,520,250,100,'Provider Machine','orange'),'mtx':(1110,160,250,100,'Public MediaMTX Host if Streaming','orange'),'ext':(1490,160,230,100,'OBS Browser Capture Destination','gray')},
        [('browser','vercel','static'),('browser','api','API'),('api','db','database'),('provider','api','HTTPS'),('ext','mtx','media'),('mtx','api','auth'),('provider','mtx','media')])
    for name,(nodes,edges) in diagrams.items():
        file=ASSETS/f'{name}.png'; diagram(file,name.replace('_',' ').title(),nodes,edges); diagrams[name]=file
    return diagrams

def find(doc, starts):
    for p in doc.paragraphs:
        if p.text.strip().startswith(starts): return p
    raise KeyError(starts)

def delete_para(p):
    p._element.getparent().remove(p._element)

def remove_static_toc(doc):
    title=find(doc,'TABLE OF CONTENTS')
    active=False
    for p in list(doc.paragraphs):
        if p is title: active=True; continue
        if active and p.text.strip().startswith('CHAPTER 1 INTRODUCTION'): break
        if active: delete_para(p)
    return title

def toc_after(doc, anchor):
    p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.LEFT; p.paragraph_format.space_after=Pt(8)
    r=p.add_run(); fld1=OxmlElement('w:fldChar'); fld1.set(qn('w:fldCharType'),'begin'); instr=OxmlElement('w:instrText'); instr.set(qn('xml:space'),'preserve'); instr.text=' TOC \\o "1-3" \\h \\z \\u '; fld2=OxmlElement('w:fldChar'); fld2.set(qn('w:fldCharType'),'separate'); txt=OxmlElement('w:t'); txt.text='Right-click and select Update Field to refresh the table of contents.'; fld3=OxmlElement('w:fldChar'); fld3.set(qn('w:fldCharType'),'end'); r._r.extend([fld1,instr,fld2,txt,fld3]); font(r,11)
    return move_after(p,anchor)

def normalize(doc):
    for name in ['Normal','Heading 1','Heading 2','Heading 3']:
        st=doc.styles[name]; st.font.name='Times New Roman'; st._element.rPr.rFonts.set(qn('w:ascii'),'Times New Roman'); st._element.rPr.rFonts.set(qn('w:hAnsi'),'Times New Roman'); st.font.color.rgb=RGBColor(0,0,0)
    for p in doc.paragraphs:
        for r in p.runs:
            if r.font.name: font(r, r.font.size.pt if r.font.size else 11, r.bold, r.italic, BLACK, 'Times New Roman' if r.font.name!='Consolas' else 'Consolas')
    settings=doc.settings.element; node=OxmlElement('w:updateFields'); node.set(qn('w:val'),'true'); settings.append(node)

def expand_chapter_1(doc):
    a=find(doc,'1.4 Significance and Boundaries')
    a=para_after(doc,a,'1.5 Target Users and Stakeholders',2)
    a=para_after(doc,a,'Nexora serves three technical stakeholder groups. End users submit and inspect workloads through the browser dashboard. Provider operators run the Python agent on machines whose compute capacity they choose to contribute; the agent reports local capability rather than granting remote shell access to the control plane. Project evaluators and maintainers use the backend APIs, database records, audit events, configuration and tests to understand how the platform behaves. This separation gives every participant a defined responsibility: users request work, the control plane coordinates it, and providers execute it locally.')
    a=para_after(doc,a,'1.6 Representative Use Cases',2)
    a=table_after(doc,a,['Use case','User action','Control-plane outcome','Provider outcome'],[
        ('Controlled computation','Submit a matrix, prime-search or Fibonacci request','Validate requirements, reserve tokens and schedule a compatible provider','Poll, execute, checkpoint and report result'),
        ('Video processing','Upload a supported video then create a compression job','Probe artifact, attach metadata and select FFmpeg-capable provider','Download input, transcode and upload output'),
        ('Provider participation','Start the provider agent on a machine','Store capacity, status and last heartbeat','Measure local resource state and poll work'),
        ('Recovery demonstration','Allow heartbeat to exceed configured timeout','Create recovery attempt or fail/refund when no replacement exists','Resume checkpoint-capable workload when assigned'),
        ('Streaming demonstration','Create an OBS or browser-capture session','Allocate stream-capable provider and session credentials','Use FFmpeg to consume media and publish encoded output'),
    ],[1.2,1.65,2.0,1.65],7.4)
    a=caption_after(doc,a,'Table 1.2','Representative Nexora use cases and responsibilities')
    a=para_after(doc,a,'1.7 Functional and Non Functional Requirements',2)
    a=table_after(doc,a,['Category','Requirement derived from implementation'],[
        ('Functional','Create and validate accounts; authenticate sessions; register providers; submit and cancel jobs; track progress, checkpoints, artifacts and token activity.'),
        ('Functional','Report current CPU, RAM, disk and optional GPU/FFmpeg capability; select compatible provider based on request constraints.'),
        ('Functional','Expose dashboard, provider, job, billing, artifact, checkpoint and optional streaming interfaces through REST and realtime topics.'),
        ('Non functional','Persist application state through SQLAlchemy, reject malformed request bodies through Pydantic constraints, and restrict user-owned job/artifact access.'),
        ('Non functional','Allow local development, Docker Compose topology and split static frontend/backend deployment configuration.'),
        ('Constraint','Provider connectivity is polling based; current cloud/media deployments, external payment and distributed high availability are outside verified scope.'),
    ],[1.2,5.3],8.3)
    a=caption_after(doc,a,'Table 1.3','Functional and non functional requirements')
    a=para_after(doc,a,'1.8 Design Constraints',2)
    a=para_after(doc,a,'The design favors a compact prototype that can be read end to end. Consequently, backend routes, database models, scheduler behavior and realtime infrastructure occupy one FastAPI module, and provider behavior occupies one Python module. This choice reduces the number of deployment units for an academic demonstration but increases coupling. A second constraint is network reachability: the provider initiates its own registration, heartbeat and polling calls, making it easier to operate behind common network boundaries. A final constraint is evidence discipline: external services may be configured by the repository, but they are described as configured integrations unless execution evidence exists.')

def expand_chapter_2(doc):
    a=find(doc,'2.5 Artifact Processing, Streaming and Token Accounting')
    a=para_after(doc,a,'2.6 Related Work and Design Position',2)
    a=para_after(doc,a,'Research on cloud, edge and fog scheduling treats heterogeneous capacity, response time, cost, utilization and reliability as competing objectives. Recent surveys group scheduling approaches into deterministic, heuristic, metaheuristic and learning-based families [3]-[5]. Nexora intentionally chooses a transparent deterministic rule: it rejects incompatible providers and selects the candidate with the minimum cost adjusted by the stored reliability value. This is appropriate for an inspectable academic prototype because the decision can be traced directly to provider attributes. It is not presented as a replacement for fair-share, backfilling, predictive or reinforcement-learning scheduling.')
    a=para_after(doc,a,'Checkpoint-restart research explains why saved state can improve fault recovery and resource use: a failed computation can continue from a retained recovery point rather than beginning again [6]. Nexora uses application-level checkpoints rather than transparent process snapshots. Its checkpoint payload is workload-specific, has a canonical hash, and is associated with a sequence and attempt number. That choice keeps the storage model simple but means arbitrary custom Python processes cannot be migrated transparently; the provider deliberately restarts that workload from the beginning on recovery.')
    a=para_after(doc,a,'2.7 Security Concepts Applied to Nexora',2)
    a=para_after(doc,a,'The authentication design combines password hashing, JWTs and server-side session records. The backend uses PBKDF2-HMAC-SHA256 with a generated salt and 600,000 iterations. Python documentation describes PBKDF2-HMAC as a password-based key derivation function and notes that iteration count should reflect contemporary computing power [7]. Nexora additionally validates session state on every protected request, so a missing, revoked or expired session is rejected even when a token is structurally valid. WebSocket credentials are placed in a subprotocol header rather than a URL. These controls protect normal user sessions; they do not eliminate the separate provider-identity limitation described in Chapter 5.')
    a=para_after(doc,a,'2.8 Comparative Concept Table',2)
    a=table_after(doc,a,['Concept','General objective','Nexora realization','Academic interpretation'],[
        ('Heterogeneous scheduling','Map work to differing capacities','CPU/RAM/GPU/FFmpeg eligibility then cost/reliability ordering','Rule-based baseline'),
        ('Control plane','Coordinate state and policy','FastAPI routes, models, scheduler and realtime hub','Central coordination boundary'),
        ('Provider agent','Execute work near resources','Python agent with psutil, requests, FFmpeg probe and worker functions','Execution-plane representative'),
        ('Checkpoint recovery','Reduce loss from failure','State payload, hashes, attempts and replacement assignment','Application-level recovery'),
        ('Realtime monitoring','Expose current state','REST snapshots plus authenticated WebSocket events','Current-state observability'),
        ('Accounting','Associate use with balance','Wallet, token ledger, reservation and settlement','Demonstration accounting model'),
    ],[1.3,1.6,2.4,1.45],7.4)
    a=caption_after(doc,a,'Table 2.2','Core concepts, Nexora adaptation and design position')

def expand_chapter_3(doc, figs):
    a=find(doc,'3.3.5 Logging and artifact locations')
    a=para_after(doc,a,'3.4 User Authentication and Provider Registration Flow',2)
    a=para_after(doc,a,'Figure 3.3 shows the distinct trust paths. A user register/login operation creates or validates credentials and returns a JWT tied to a durable session identifier. Subsequent user requests carry a bearer token. A provider follows another path: it collects capacity metadata and sends it with `X-Provider-Token`; the control plane creates or updates the provider record. These paths meet at the scheduling layer but retain different authorization checks.')
    a=image_after(doc,a,figs['auth']); a=caption_after(doc,a,'Figure 3.3','User session creation and protected-access flow')
    a=para_after(doc,a,'3.5 Provider Heartbeat and Telemetry Flow',2)
    a=para_after(doc,a,'The provider reads its local operating-system and hardware state before registration. After registration it sends utilization heartbeats at the configured interval. The backend overwrites current utilization and last-heartbeat fields, publishes telemetry events, and the frontend merges events into its client-side state. Figure 3.4 makes explicit that the project presents current telemetry rather than a historical metrics database.')
    a=image_after(doc,a,figs['heartbeat']); a=caption_after(doc,a,'Figure 3.4','Provider discovery, registration, heartbeat and telemetry publication')
    a=para_after(doc,a,'3.6 Job Submission Scheduling and Dispatch Methodology',2)
    a=para_after(doc,a,'The scheduling methodology is request driven. The backend copies the workload into a requirements map, validates workload-specific prerequisites, evaluates each provider, reserves tokens, and stores a scheduled job. The provider then obtains its own pending work through polling rather than the backend directly connecting to it. Figure 3.5 traces each decision and identifies the point where token reservation occurs before provider execution.')
    a=image_after(doc,a,figs['schedule']); a=caption_after(doc,a,'Figure 3.5','Job submission, provider selection, dispatch and settlement flow')
    a=para_after(doc,a,'3.7 Recovery and State Management Methodology',2)
    a=para_after(doc,a,'The recovery monitor is a background thread started through the application lifespan. It periodically evaluates active providers against a heartbeat timeout. For each affected job it reads the latest checkpoint, searches for an alternative compatible provider, increments the attempt, records recovery metadata and relies on fencing to reject late messages from a previous attempt. Figure 3.6 distinguishes a successful recovery branch from the failure/refund branch.')
    a=image_after(doc,a,figs['recovery']); a=caption_after(doc,a,'Figure 3.6','Heartbeat-loss detection, checkpoint selection and fenced recovery')
    a=para_after(doc,a,'3.8 Data Model and Ownership Methodology',2)
    a=para_after(doc,a,'The database is ownership-oriented. Users own sessions, wallets, jobs and user artifacts. Jobs optionally reference providers and have checkpoints, billing records and related artifacts. Stream sessions link user, provider, encrypted destination state and accounting data. This model enables user-specific job/artifact retrieval and allows provider activity to be reflected in persistent records. Figure 3.7 summarizes the entity groups; Chapter 4 and Appendix A enumerate fields and relationships.')
    a=image_after(doc,a,figs['architecture']); a=caption_after(doc,a,'Figure 3.7','Component and data-store relationships across the Nexora architecture')

def expand_chapter_4(doc, figs):
    a=find(doc,'4.10 Remote Live Stream Encoding')
    a=para_after(doc,a,'4.11 Frontend Page by Page Behavior',2)
    a=table_after(doc,a,['Page','Purpose and controls','Data and resulting state'],[
        ('Landing','Explains product concept; opens authentication interaction; exposes a client-side scheduling simulator.','Public view; no authenticated backend page data required.'),
        ('Overview','Displays active job count, available nodes, token balance, utilization summaries, recent jobs and charts.','Dashboard API snapshot plus provider/telemetry/job events update state.'),
        ('Jobs','Searches jobs, opens job creation modal, accepts supported video input, opens a drawer and can cancel/stop all.','Jobs and artifact APIs create/inspect/update user-owned jobs.'),
        ('Providers','Lists provider capacity, status, reliability and current utilization.','Provider list plus realtime provider-status events.'),
        ('Resource pool','Lets a user vary conditions and inspect candidate filtering.','Client-side simulation based on available provider data; not persistent scheduler configuration.'),
        ('Billing','Shows balance, package options, ledger activity and demo top-up form.','Billing APIs change application token state; payment itself is simulated.'),
        ('Analytics and settings','Shows total jobs/success ratio/recovering count; sets API base/theme/polling behavior.','Analytics API and browser-local settings/health check.'),
        ('Streaming','Creates OBS/browser-capture session, shows credentials/status/metrics and stops session.','Stream session REST, WebSocket updates and browser WHIP helper where selected.'),
    ],[1.25,3.15,2.25],7.2)
    a=caption_after(doc,a,'Table 4.1','Frontend pages, user controls and state relationships')
    a=para_after(doc,a,'The frontend follows a small explicit architecture. `router.js` parses the hash and redirects unauthenticated console routes to the landing page. `state.js` owns the shared dashboard snapshot and prevents overlapping refreshes. `realtime.js` subscribes to server topics, sends periodic pings, reconnects when necessary and asks for a REST resynchronization when an event requires it. `api.js` centralizes bearer-token headers, configured API base selection and error-message extraction. This design makes page components thin: they render state and invoke named API helpers rather than implementing their own transport logic.')
    a=para_after(doc,a,'4.12 Backend Module Structure and Lifecycle',2)
    a=para_after(doc,a,'The FastAPI application is intentionally consolidated into `app/main.py`. Imports and environment loading are followed by database setup, model declarations, request schemas, lifecycle tasks, real-time support, authentication helpers, scheduling/billing functions and route definitions. At lifespan startup the application establishes the realtime event loop, attempts media configuration validation without disabling non-stream features, creates ORM tables, applies selected SQLite compatibility columns, ensures wallets for users and starts the recovery monitor. On shutdown it signals the monitor to stop and closes realtime clients. This lifecycle approach makes state initialization reproducible for a single application process.')
    a=para_after(doc,a,'4.13 Password Hashing JWT Sessions and Access Checks',2)
    a=para_after(doc,a,'The password helper generates a random 16-byte salt and derives a PBKDF2-HMAC-SHA256 digest. The stored representation records the algorithm, iteration count, salt and digest. Login uses a timing-safe comparison. `session_response` generates a durable session identifier with a twelve-hour expiry, stores it in `auth_sessions`, creates a JWT with `sub`, `sid`, email and `exp` claims, and returns a user object with current token balance. `current_user` decodes the token and verifies the referenced session. User-owned access is subsequently enforced by filters such as `job.user_id == u.id` and `artifact.user_id == u.id`.')
    a=code_after(doc,a,'''def current_user(authorization: str = Header(...), s: Session = Depends(db)):
    payload = jwt.decode(authorization.removeprefix("Bearer "), JWT_SECRET,
                         algorithms=["HS256"])
    session = s.get(AuthSession, payload["sid"])
    if not session or session.revoked or session.expires_at < now:
        raise HTTPException(401, "Invalid or expired session")
    return s.get(User, int(payload["sub"]))''')
    a=caption_after(doc,a,'Listing 4.1','Condensed session-validation behavior derived from `current_user`')
    a=para_after(doc,a,'4.14 Provider Eligibility and Selection Algorithm',2)
    a=para_after(doc,a,'The `compatible_provider` function implements the scheduler decision. It identifies workload-specific minimum CPU and RAM requirements, excludes the failed provider during recovery, considers only ONLINE or AVAILABLE providers, checks requested GPU presence, and requires FFmpeg/encoder capability for video compression or streaming. For remote streaming it additionally excludes providers with active stream sessions. Among survivors it selects the minimum of `cost_per_hour / (max(reliability, 1) / 100)`. A lower cost and a higher reliability value reduce the effective score. The function returns no candidate when every provider fails a rule, causing the job creation route to return a clear conflict response rather than creating an unschedulable job.')
    a=image_after(doc,a,figs['schedule']); a=caption_after(doc,a,'Figure 4.1','Detailed eligibility, scoring and dispatch sequence')
    a=para_after(doc,a,'4.15 Job State Transitions and Execution Updates',2)
    a=table_after(doc,a,['State','Entered by','Meaning and next actions'],[
        ('SCHEDULED','Backend job creation','Provider selected and tokens reserved; provider polling may retrieve job.'),
        ('RUNNING','Provider update','Execution began; started time recorded when absent; progress and checkpoints may follow.'),
        ('RECOVERING','Recovery monitor','Lost provider is replaced; attempt increases and resume metadata is supplied.'),
        ('COMPLETED','Provider update','Result recorded; provider returned ONLINE; reservation settled to actual usage.'),
        ('FAILED','Provider or recovery monitor','Failure result persisted; reservation settlement/refund behavior applies.'),
        ('CANCELLED','User cancel/stop-all','Application state records cancellation; provider-stop coverage is a future reliability item.'),
    ],[1.2,1.45,4.0],8.2)
    a=caption_after(doc,a,'Table 4.2','Job states, authors and resulting control-plane behavior')
    a=para_after(doc,a,'The update route uses an attempt number as a fencing token. A provider message whose attempt does not match the stored attempt is rejected with HTTP 409. This prevents a late result from the failed provider attempt from overwriting a newer recovery attempt. The provider sends RUNNING before execution, progress/checkpoints during supported workloads and a terminal update with an elapsed duration/result payload. When a terminal update still has reserved tokens, the backend performs idempotent settlement by clearing the reservation, returning it to the wallet and debiting actual successful usage where applicable.')
    a=para_after(doc,a,'4.16 Checkpoint Storage Integrity and Recovery',2)
    a=para_after(doc,a,'Checkpoint requests are accepted only for existing jobs and current attempts. The backend computes a canonical JSON hash for state payloads and rejects a supplied nonmatching hash. It assigns a sequence number when one is not supplied and stores the provider identifier, attempt, progress, state version, hash, payload and timestamp. Latest and historical checkpoint routes make the state available to authenticated providers, while the user checkpoint route joins jobs to limit results to the caller. On recovery, the provider obtains the latest valid checkpoint and passes workload-specific resume state into matrix/prime/Fibonacci functions. Arbitrary custom Python does not claim transparent memory migration; it cleanly starts again.')
    a=para_after(doc,a,'4.17 Artifact Upload Validation and Video Processing',2)
    a=para_after(doc,a,'User video upload begins with extension and MIME allow lists. The server reads the uploaded file in chunks into an artifact-specific directory while enforcing a configured maximum byte count. It resolves FFmpeg through PATH or imageio-ffmpeg and probes duration, dimensions, codec, frame rate and audio presence. The route rejects a missing/invalid video or duration above the configured limit, computes a SHA-256 checksum, stores metadata in `job_artifacts`, records an audit event and returns non-sensitive metadata. The job creation route verifies that a video compression input artifact belongs to the authenticated user before attaching it to the job. The provider later downloads the matching input path, creates an output and uploads the result artifact.')
    a=image_after(doc,a,figs['artifact']); a=caption_after(doc,a,'Figure 4.2','Artifact upload, validation, provider transfer and output ownership flow')
    a=para_after(doc,a,'4.18 Token Wallet Reservation Settlement and Refunds',2)
    a=para_after(doc,a,'Token accounting is server owned. `wallet_for` creates a wallet and initial adjustment only where a user has no wallet. `token_ledger` records transaction type, signed amount, balance before/after, reference type, reference ID, description and optional job ID; it rejects a debit that would make the balance negative. `estimate_tokens` derives a reservation from workload requirements. Job creation creates both a negative reservation transaction and a `job_billing` record. Terminal successful completion uses the reported elapsed seconds to calculate a bounded actual token amount, returns the reservation and debits usage. Failure or provider loss can return an outstanding reservation. Package purchase and demo top-up are application token credits rather than card-network charges.')
    a=image_after(doc,a,figs['wallet']); a=caption_after(doc,a,'Figure 4.3','Wallet creation, reservation, settlement, refund and simulated purchase flow')
    a=para_after(doc,a,'4.19 REST API and WebSocket Topic Design',2)
    a=table_after(doc,a,['API group','Representative routes','Authentication','Primary effect'],[
        ('Identity','POST /auth/register; POST /auth/login','Public','User/session creation or token return'),
        ('User workload','GET/POST /jobs; POST /jobs/{id}/cancel; GET /checkpoints','Bearer JWT','Create, inspect and alter owned job state'),
        ('Provider','POST /providers/register; heartbeat; pending; update; checkpoint','Provider token','Capacity state and execution lifecycle'),
        ('Artifacts','upload, metadata, user download, provider download/output upload','JWT or provider token','Transfer and ownership-controlled file access'),
        ('Billing','GET /billing; transactions; purchase; demo-topup','Bearer JWT','Read/change application token ledger'),
        ('Streaming','stream sessions, claim, heartbeat, stopped, MediaMTX auth','Context-specific','Allocate and supervise stream session'),
        ('Realtime','WS /ws/realtime','JWT in subprotocol','Topic subscription and event delivery'),
    ],[1.15,2.85,1.25,1.8],7.4)
    a=caption_after(doc,a,'Table 4.3','Representative REST and realtime interface groups')
    a=para_after(doc,a,'The realtime endpoint accepts subscriptions to telemetry, providers, jobs, checkpoints, billing, resources and streams. It checks browser origin, authenticates a token carried in the WebSocket protocol list, caps connection/message characteristics, validates topic names and responds to a ping. The server publishes already committed state changes. The frontend still treats REST reads as authoritative and uses a refresh after reconnect or event-driven resync, preventing the realtime channel from becoming a separate persistence source.')
    a=para_after(doc,a,'4.20 Stream Sessions MediaMTX Authorization and FFmpeg',2)
    a=para_after(doc,a,'A stream-session request validates that its source mode is OBS or browser capture, destination platform is YouTube/Twitch/custom RTMP, profile exists, wallet balance meets the minimum, destination uses RTMP or RTMPS and does not resolve to forbidden local/internal addresses. The backend then selects a provider with capacity, FFmpeg availability and a usable H.264 encoder. It stores an allocated `stream_sessions` record containing a generated session ID, publish/read keys, encrypted destination key, profile/encoder configuration, token rate and state metrics. The owner obtains session credentials only through authorized calls; the provider receives the destination credentials only after a single-use claim of its assigned session.')
    a=image_after(doc,a,figs['stream']); a=caption_after(doc,a,'Figure 4.4','Remote streaming session, MediaMTX authorization and provider FFmpeg pathway')
    a=para_after(doc,a,'The MediaMTX callback authenticates publish/read attempts against the active session path and credential. The provider stream runner creates FFmpeg arguments for the chosen profile, parses progress, reports valid stream state and asks the backend for continue/stop action through heartbeat. The backend accrues stream tokens only while state is STREAMING and at least a full minute has elapsed. On a final stopped message it stores metrics/errors, releases the provider and clears the session credentials. This is a fully specified repository workflow, while a real public broadcast still depends on separately operating MediaMTX, networking and destination credentials.')

def expand_chapter_5(doc, figs):
    a=find(doc,'5.6 Deployment Topology')
    a=para_after(doc,a,'5.7 Component Level Results Analysis',2)
    a=table_after(doc,a,['Subsystem','What source demonstrates','User or operator value','Evidence type'],[
        ('Frontend console','Nine routes, page modules, authentication guard, API wrapper, shared state and realtime reconnection','One interface for jobs, providers, billing, analytics and streams','Source inspection; frontend utility tests'),
        ('Control plane','Persistent models, route groups, scheduler, recovery loop and websocket hub','Centralized state and decisions','Source inspection; Python parse check'),
        ('Provider agent','Hardware probes, heartbeats, polling, workload handlers and FFmpeg runner','Local execution while retaining control-plane coordination','Source inspection'),
        ('Persistence','Users, sessions, providers, jobs, checkpoints, artifacts, wallet/ledger, audit and streams','Traceable ownership and lifecycle data','ORM declarations/configuration'),
        ('Media path','Session credentials, callback checks and FFmpeg progress handling','Structured optional streaming demonstration','Source/config/test inventory'),
    ],[1.25,2.25,1.8,1.45],7.1)
    a=caption_after(doc,a,'Table 5.4','Component-level implementation analysis')
    a=para_after(doc,a,'5.8 Scheduling Telemetry Billing Artifact and Streaming Analysis',2)
    a=para_after(doc,a,'Scheduling is transparent and easy to audit: every selection begins by eliminating incompatible resources, then applies a single score rather than hiding allocation behind a black-box model. This makes it suitable for explaining why a request cannot be scheduled and for demonstrating capacity-aware selection. Telemetry is intentionally current-state focused; it gives the dashboard a practical operational view of provider CPU, RAM, disk and optional GPU values. Billing connects an action to a durable token ledger before and after job execution. Artifact flow establishes provenance through owner association, checksum and metadata. Streaming extends the same provider-selection and accounting principles to a session-oriented media workload.')
    a=para_after(doc,a,'5.9 Deployment and Operational Considerations',2)
    a=para_after(doc,a,'Figure 5.3 describes the supported deployment alternatives. The static dashboard can be served locally or through Vercel. The control plane can run directly, in Docker Compose or through the Render Blueprint. SQLite is appropriate for the default direct demonstration, while Compose/Render configuration makes PostgreSQL available for a more durable service topology. Providers remain separate processes and must target the same backend and credential configuration. The media plane is deliberately separate because MediaMTX needs network listeners that ordinary web hosting does not provide.')
    a=image_after(doc,a,figs['deploy']); a=caption_after(doc,a,'Figure 5.3','Local, hosted and media deployment topology')
    a=para_after(doc,a,'5.10 Focused Limitations and Engineering Implications',2)
    a=para_after(doc,a,'The codebase has a clear prototype boundary. Custom Python execution is flexible but needs true workload isolation before it is exposed to untrusted users. The shared provider token simplifies setup but should be replaced with per-provider enrollment and revocation. Polling dispatch should gain an atomic lease/claim so concurrent agent activity cannot start duplicated work. Application cancellation should send a provider-visible stop command and perform one idempotent settlement. Artifact paths should evolve from backend-local storage to capacity-controlled durable storage. The in-memory realtime/recovery mechanism is appropriate to a single process but would require a distributed coordination design for replicas. These are focused engineering improvements; they do not invalidate the implemented workflows described above.')

def expand_chapter_6(doc):
    a=find(doc,'6.2 Future Enhancements')
    a=para_after(doc,a,'6.3 Prioritized Engineering Roadmap',2)
    a=para_after(doc,a,'The immediate roadmap strengthens trust and execution safety: introduce per-provider identity, isolate untrusted workloads, and establish atomic dispatch/cancel acknowledgements. The next stage makes state operationally durable through migrations, PostgreSQL policy, artifact lifecycle management and telemetry history. The final stage increases usability and scale through provider pools, labels, quotas, fairness policies, administrative roles, structured observability and fully automated integration testing. This sequence preserves the current educational value of a simple control plane while addressing the requirements that matter before broader deployment.')

def expand_appendix(doc):
    a=find(doc,'B.4 Final Audit Notes')
    a=para_after(doc,a,'B.5 API Request and Response Examples',3)
    a=para_after(doc,a,'The following examples are schematic representations of the actual request schemas and response fields. Values are illustrative only and do not represent captured production data or credentials.')
    a=code_after(doc,a,'''POST /jobs
Authorization: Bearer <session-token>
{
  "name": "Matrix Benchmark",
  "workload": "matrix_multiply",
  "requirements": {"matrix_size": 300, "expected_runtime_hours": 0.05}
}

201/200 response shape
{
  "id": "job_<generated>", "status": "SCHEDULED",
  "provider_id": "provider_<assigned>", "estimated_tokens": 6,
  "reserved_tokens": 6, "progress": 0
}''')
    a=caption_after(doc,a,'Listing B.2','Illustrative job creation schema and response fields')
    a=code_after(doc,a,'''POST /providers/<provider-id>/heartbeat
X-Provider-Token: <configured-provider-token>
{
  "status": "ONLINE",
  "utilization": {"cpu": 22.1, "ram": 48.0,
                  "disk": 51.4, "gpu_memory": null, "gpu_compute": null}
}

Response: {"ok": true}''')
    a=caption_after(doc,a,'Listing B.3','Illustrative provider heartbeat schema')
    a=para_after(doc,a,'B.6 Detailed Database Field Summary',3)
    a=table_after(doc,a,['Entity','Important fields','Ownership/constraint'],[
        ('users','id, email, password_hash, wallet_balance','email unique; user root entity'),
        ('providers','id, name, cpu_cores, ram_gb, GPU fields, status, reliability, utilization, system_info, last_heartbeat','provider ID primary key'),
        ('jobs','id, name, workload, requirements, status, progress, user_id, provider_id, attempt, recovery_count, result, timestamps','user and optional provider foreign keys'),
        ('checkpoints','id, job_id, provider_id, attempt, seq, progress, state_version, state_hash, payload','job foreign key; application-level sequence'),
        ('auth_sessions','id, user_id, issued_at, expires_at, revoked','user foreign key/index'),
        ('job_artifacts','id, job_id, user_id, file_path, checksum_sha256, meta_data, content','user ownership; job optional until assignment'),
        ('wallets and token_transactions','token_balance; ledger type/amount/before/after/reference','wallet unique by user; ledger references wallet/user/job'),
        ('stream_sessions','user_id, provider_id, status, keys, destination fields, profile, metrics, billing times','session-scoped media/accounting state'),
    ],[1.35,3.75,1.7],7.0)
    a=caption_after(doc,a,'Table B.2','Detailed data-entity field and ownership summary')

def build():
    doc=Document(BASE)
    normalize(doc)
    toc_title=remove_static_toc(doc); toc_after(doc,toc_title)
    figs=make_diagrams()
    expand_chapter_1(doc); expand_chapter_2(doc); expand_chapter_3(doc,figs); expand_chapter_4(doc,figs); expand_chapter_5(doc,figs); expand_chapter_6(doc); expand_appendix(doc)
    # core metadata
    doc.core_properties.title='Nexora Unified Compute Management Platform PBC Project Report'
    doc.core_properties.subject='Project Based Component report for Nexora Unified Compute Management Platform'
    doc.core_properties.author='[Student Name]'
    doc.core_properties.comments='Generated from supplied project evidence and reference format.'
    doc.save(FINAL)

if __name__=='__main__': build()
