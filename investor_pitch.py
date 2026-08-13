#!/usr/bin/env python3
"""Investor Pitch: Private Lending Opportunity — Montgomery, Alabama"""

from googleapiclient.discovery import build
from google.oauth2 import service_account
import time

SCOPES   = ['https://www.googleapis.com/auth/documents']
CREDS    = r'D:\Dropbox\J Feels\Dev\foreclosure-agent\credentials.json'
DOC_ID   = '1jePBZRD4YuLvaQkkJfxhcHTNmJZstSJxOSiQZG5y8_c'

# ── Palette ────────────────────────────────────────────────────────────────────
def rgb(r,g,b): return {'red':r/255,'green':g/255,'blue':b/255}
NAVY  = rgb(15,52,96);   GOLD  = rgb(180,145,55);  WHITE = rgb(255,255,255)
EVEN  = rgb(238,244,252); DARK = rgb(30,30,30);     BODY  = rgb(60,60,60)
TEAL  = rgb(39,174,96);  LGRAY = rgb(245,248,252)

# ── Service ────────────────────────────────────────────────────────────────────
def get_svc():
    creds = service_account.Credentials.from_service_account_file(CREDS, scopes=SCOPES)
    return build('docs','v1',credentials=creds)

def batch(svc, reqs):
    if reqs:
        svc.documents().batchUpdate(documentId=DOC_ID, body={'requests':reqs}).execute()
        time.sleep(0.5)

def read_doc(svc):
    return svc.documents().get(documentId=DOC_ID).execute()

def clear_doc(svc):
    doc = read_doc(svc)
    end = doc['body']['content'][-1]['endIndex'] - 1
    if end > 1:
        batch(svc,[{'deleteContentRange':{'range':{'startIndex':1,'endIndex':end}}}])

# ── Writer ─────────────────────────────────────────────────────────────────────
class W:
    def __init__(self):
        self.reqs = []; self.pos = 1

    def _ins(self, text):
        s = self.pos
        self.reqs.append({'insertText':{'location':{'index':s},'text':text}})
        self.pos += len(text)
        return s

    def _ps(self, s, e, named=None, align=None, sa=None, sb=None, is_=None):
        ps, flds = {}, []
        if named:  ps['namedStyleType'] = named;                             flds.append('namedStyleType')
        if align:  ps['alignment']       = align;                            flds.append('alignment')
        if sa:     ps['spaceAbove']       = {'magnitude':sa,'unit':'PT'};    flds.append('spaceAbove')
        if sb:     ps['spaceBelow']       = {'magnitude':sb,'unit':'PT'};    flds.append('spaceBelow')
        if is_:    ps['indentStart']      = {'magnitude':is_,'unit':'PT'};   flds.append('indentStart')
        if flds:
            self.reqs.append({'updateParagraphStyle':{
                'range':{'startIndex':s,'endIndex':e},
                'paragraphStyle':ps,'fields':','.join(flds)}})

    def _ts(self, s, e, bold=False, italic=False, fs=None, color=None, font=None):
        ts, flds = {}, []
        if bold:   ts['bold']   = True;                                      flds.append('bold')
        if italic: ts['italic'] = True;                                      flds.append('italic')
        if fs:     ts['fontSize'] = {'magnitude':fs,'unit':'PT'};            flds.append('fontSize')
        if color:  ts['foregroundColor'] = {'color':{'rgbColor':color}};     flds.append('foregroundColor')
        if font:   ts['weightedFontFamily'] = {'fontFamily':font};           flds.append('weightedFontFamily')
        if flds:
            self.reqs.append({'updateTextStyle':{
                'range':{'startIndex':s,'endIndex':e},
                'textStyle':ts,'fields':','.join(flds)}})

    # ── content helpers ──────────────────────────────────────────────────────
    def title(self, text):
        s = self._ins(text+'\n'); e = self.pos
        self._ps(s,e,named='TITLE',align='CENTER',sa=0,sb=6)
        self._ts(s,e-1,bold=True,fs=26,color=NAVY,font='Montserrat')

    def subtitle(self, text):
        s = self._ins(text+'\n'); e = self.pos
        self._ps(s,e,named='SUBTITLE',align='CENTER',sa=0,sb=4)
        self._ts(s,e-1,fs=14,color=GOLD,font='Montserrat')

    def rule(self):
        s = self._ins('━'*55+'\n'); e = self.pos
        self._ps(s,e,named='NORMAL_TEXT',align='CENTER',sa=14,sb=14)
        self._ts(s,e-1,fs=9,color=GOLD)

    def h1(self, text, color=None):
        c = color or NAVY
        s = self._ins(text+'\n'); e = self.pos
        self._ps(s,e,named='HEADING_1',sa=22,sb=6)
        self._ts(s,e-1,bold=True,fs=15,color=c,font='Montserrat')

    def h2(self, text, color=None):
        c = color or NAVY
        s = self._ins(text+'\n'); e = self.pos
        self._ps(s,e,named='HEADING_2',sa=14,sb=4)
        self._ts(s,e-1,bold=True,fs=12,color=c,font='Montserrat')

    def h3(self, text):
        s = self._ins(text+'\n'); e = self.pos
        self._ps(s,e,named='HEADING_3',sa=10,sb=3)
        self._ts(s,e-1,bold=True,fs=11,color=NAVY,font='Montserrat')

    def p(self, text, bold=False, italic=False, color=None, fs=11,
          sa=0, sb=7, align=None):
        c = color or BODY
        s = self._ins(text+'\n'); e = self.pos
        self._ps(s,e,named='NORMAL_TEXT',sa=sa,sb=sb,align=align)
        self._ts(s,e-1,fs=fs,color=c,bold=bold,italic=italic,font='Merriweather')

    def bullet(self, text, bold=False):
        s = self._ins(text+'\n'); e = self.pos
        self.reqs.append({'createParagraphBullets':{
            'range':{'startIndex':s,'endIndex':e},
            'bulletPreset':'BULLET_DISC_CIRCLE_SQUARE'}})
        self._ps(s,e,named='NORMAL_TEXT',sa=2,sb=3)
        self._ts(s,e-1,fs=11,color=BODY,bold=bold,font='Merriweather')

    def blank(self):
        self._ins('\n')

    def placeholder(self, name):
        s = self._ins(f'__TABLE_{name}__\n'); e = self.pos
        self._ps(s,e,named='NORMAL_TEXT',sa=2,sb=2)
        self._ts(s,e-1,fs=6,color=WHITE)  # invisible white text


# ── Table utilities ────────────────────────────────────────────────────────────
def find_placeholder(svc, name):
    doc = read_doc(svc)
    target = f'__TABLE_{name}__'
    for elem in doc['body']['content']:
        if 'paragraph' in elem:
            text = ''.join(r.get('textRun',{}).get('content','')
                           for r in elem['paragraph'].get('elements',[]))
            if target in text:
                return elem['startIndex'], elem['endIndex']
    return None, None

def insert_table(svc, name, headers, rows):
    """Replace placeholder with a formatted table."""
    p_start, p_end = find_placeholder(svc, name)
    if p_start is None:
        print(f"  WARNING: placeholder __TABLE_{name}__ not found"); return

    # Delete placeholder
    batch(svc,[{'deleteContentRange':{'range':{'startIndex':p_start,'endIndex':p_end}}}])

    # Insert empty table
    nr = len(rows)+1; nc = len(headers)
    batch(svc,[{'insertTable':{'rows':nr,'columns':nc,'location':{'index':p_start}}}])

    # Read to find cell positions
    doc = read_doc(svc)
    table_elem = next((e for e in doc['body']['content']
                       if 'table' in e and e['startIndex'] >= p_start-2), None)
    if not table_elem:
        print(f"  WARNING: table not found after insert for {name}"); return

    t_start = table_elem['startIndex']
    all_data = [headers] + rows
    cell_info = []
    for r_i, row_obj in enumerate(table_elem['table']['tableRows']):
        for c_i, cell_obj in enumerate(row_obj['tableCells']):
            para_idx = cell_obj['content'][0]['startIndex']
            text = str(all_data[r_i][c_i]) if r_i < len(all_data) and c_i < len(all_data[r_i]) else ''
            cell_info.append((para_idx, text, r_i==0, r_i, c_i))

    # Fill cells in reverse index order (avoids index shifting)
    cell_info.sort(key=lambda x: x[0], reverse=True)
    fill_reqs = []
    for para_idx, text, is_hdr, r_i, c_i in cell_info:
        if not text: continue
        fill_reqs.append({'insertText':{'location':{'index':para_idx},'text':text}})
        tc = WHITE if is_hdr else (NAVY if c_i == 0 else DARK)
        fill_reqs.append({'updateTextStyle':{
            'range':{'startIndex':para_idx,'endIndex':para_idx+len(text)},
            'textStyle':{
                'bold': is_hdr or c_i==0,
                'fontSize':{'magnitude':10.5,'unit':'PT'},
                'foregroundColor':{'color':{'rgbColor':tc}},
                'weightedFontFamily':{'fontFamily':'Merriweather'}},
            'fields':'bold,fontSize,foregroundColor,weightedFontFamily'}})
        fill_reqs.append({'updateParagraphStyle':{
            'range':{'startIndex':para_idx,'endIndex':para_idx+len(text)+1},
            'paragraphStyle':{
                'namedStyleType':'NORMAL_TEXT',
                'spaceAbove':{'magnitude':5,'unit':'PT'},
                'spaceBelow':{'magnitude':5,'unit':'PT'}},
            'fields':'namedStyleType,spaceAbove,spaceBelow'}})
    if fill_reqs: batch(svc, fill_reqs)

    # Re-read to get fresh table position after cell fills
    doc2 = read_doc(svc)
    table_elem2 = next((e for e in doc2['body']['content']
                        if 'table' in e and e['startIndex'] >= p_start - 5), None)
    if table_elem2:
        t_start = table_elem2['startIndex']
        use_table = table_elem2
    else:
        use_table = table_elem

    # Cell backgrounds
    bg_reqs = []
    for r_i, row_obj in enumerate(use_table['table']['tableRows']):
        for c_i in range(len(row_obj['tableCells'])):
            bg = NAVY if r_i==0 else (EVEN if r_i%2==1 else WHITE)
            bg_reqs.append({'updateTableCellStyle':{
                'tableRange':{'tableCellLocation':{
                    'tableStartLocation':{'index':t_start},
                    'rowIndex':r_i,'columnIndex':c_i},
                    'rowSpan':1,'columnSpan':1},
                'tableCellStyle':{
                    'backgroundColor':{'color':{'rgbColor':bg}},
                    'paddingTop':{'magnitude':7,'unit':'PT'},
                    'paddingBottom':{'magnitude':7,'unit':'PT'},
                    'paddingLeft':{'magnitude':12,'unit':'PT'},
                    'paddingRight':{'magnitude':12,'unit':'PT'}},
                'fields':'backgroundColor,paddingTop,paddingBottom,paddingLeft,paddingRight'}})
    if bg_reqs: batch(svc, bg_reqs)
    print(f"  OK: {name}")


# ── Document content ───────────────────────────────────────────────────────────
def build_text(svc):
    w = W()

    # Title
    w.blank()
    w.title('PRIVATE LENDING OPPORTUNITY')
    w.subtitle('Montgomery, Alabama  ·  Buy & Hold Portfolio')
    w.blank()
    w.p('Presented by  [Your Name]  |  Buying Hero Acquisitions',
        bold=True, color=DARK, fs=12, align='CENTER', sa=0, sb=2)
    w.p('March 2026  ·  Confidential',
        color=GOLD, fs=11, align='CENTER', sa=0, sb=4)
    w.rule()

    # At a Glance
    w.h1('AT A GLANCE')
    w.p('Capital Requested:  $120,000 – $150,000', bold=True, fs=12, sa=2, sb=3)
    w.p('Guaranteed Annual Return:  8%', bold=True, fs=13, color=TEAL, sa=2, sb=3)
    w.p('Minimum Term:  2 Years', bold=True, fs=12, sa=2, sb=3)
    w.p('Guaranteed Return Over 2 Years:  $19,200 – $24,000', bold=True, fs=13, color=TEAL, sa=2, sb=3)
    w.p('Deals Closed Since November 2025:  5 Properties', bold=True, fs=12, sa=2, sb=3)
    w.p('Equity Created on Example Deal:  $49,000  (29% of value)', bold=True, fs=12, color=NAVY, sa=2, sb=3)
    w.rule()

    # Executive Summary
    w.h1('EXECUTIVE SUMMARY')
    w.p('I am seeking a private lending partner to provide $120,000–$150,000 in funding '
        'to acquire and renovate single-family rental properties in Montgomery, Alabama. '
        'In exchange, I am offering a guaranteed 8% annual return on all capital deployed, '
        'with a minimum 2-year commitment. Capital is secured by each property through a '
        'promissory note and, at your option, a recorded deed of trust.', sa=0, sb=8)
    w.p('On a $150,000 loan, this represents $12,000 per year — $24,000 guaranteed over the '
        '2-year minimum. This is not a speculative investment. Every property is independently '
        'appraised before purchase by the same appraiser who works with our refinancing lender. '
        'All original capital is recovered at refinance and immediately redeployed into the next '
        'acquisition, keeping your money working at 8% continuously.', sa=0, sb=8)
    w.rule()

    # About
    w.h1('ABOUT BUYING HERO')
    w.p('Buying Hero is a professional real estate acquisition company specializing in '
        'distressed property acquisitions, with an active buy-and-hold expansion in '
        'the Montgomery, Alabama market.', sa=0, sb=8)
    w.h2('What Sets Our Approach Apart')
    w.bullet('Independent licensed appraiser performs a full CMA before every offer — '
             'the same appraiser who supports our refinancing lender')
    w.bullet('Conservative underwriting: total all-in cost must produce a minimum '
             '25–30% equity position at appraised value')
    w.bullet('5 Montgomery acquisitions closed since November 2025 — the model is proven and active')
    w.bullet('Established lender, contractor, property manager, and appraiser '
             'relationships already in place')
    w.bullet('We walk away from any deal that does not meet our margin requirements')
    w.rule()

    # Strategy
    w.h1('THE STRATEGY: BRRR')
    w.p('BRRR stands for Buy, Rehab, Rent, Refinance, Repeat — a capital-recycling model '
        'used by disciplined investors to build wealth without permanently tying up capital.',
        sa=0, sb=8)
    w.bullet('BUY — Acquire a distressed property well below market value using private capital')
    w.bullet('REHAB — Complete targeted renovations that force appreciation and achieve rental-ready condition')
    w.bullet('RENT — Lease to a qualified tenant, stabilizing income on the asset')
    w.bullet('REFINANCE — Conventional lender refinances at the new appraised value, returning all original capital')
    w.bullet('REPEAT — Returned capital is immediately deployed into the next acquisition')
    w.blank()
    w.p('Your capital is always working. Over a 2-year period, your $120,000–$150,000 can '
        'cycle through 3–4 separate acquisitions while earning 8% annually throughout.',
        bold=False, sa=4, sb=8)
    w.rule()

    # Market
    w.h1('THE MONTGOMERY, ALABAMA MARKET')
    w.h2('Alabama: Most Landlord-Friendly State in the U.S.')
    w.bullet('No rent control — statewide prohibition')
    w.bullet('Eviction process completes in under 3 weeks — among the fastest in the country')
    w.bullet('7-day notice to cure for nonpayment of rent — one of the shortest nationally')
    w.bullet('No just-cause eviction requirement')
    w.bullet('Lowest property tax rate in the nation: 0.36%')
    w.bullet('No rental license required to operate')
    w.h2('Montgomery Rental Market Fundamentals')
    w.bullet('Stable employment: Maxwell Air Force Base, Alabama state government, major universities')
    w.bullet('Military and government tenants provide consistent, recession-resistant demand')
    w.bullet('Montgomery led all Alabama cities in rent growth: +5.1% YoY  (ACRE, Aug 2025)')
    w.bullet('Active distressed inventory — strong off-market acquisition opportunity')
    w.rule()

    # The Deal
    w.h1('THE DEAL: 1160 BETH MANOR DRIVE, MONTGOMERY, AL 36109')
    w.p('This is a real, completed acquisition. Every number below is drawn from the actual transaction.',
        sa=0, sb=10)

    w.h2('Acquisition Summary')
    w.placeholder('DEAL_SUMMARY')

    w.h2('The Appraisal Process')
    w.p('Before any offer was made, our licensed appraiser performed a full Comparative Market '
        'Analysis (CMA) on the property. This is the same appraiser who works with our '
        'refinancing lender — meaning the value used to underwrite the purchase is identical '
        'to the value used to secure the bank refinance. There are no valuation surprises.',
        sa=0, sb=8)
    w.p('Confirmed After-Repair Value (ARV):  $169,000',
        bold=True, color=NAVY, fs=13, sa=4, sb=10)

    w.h3('Comparable Sales — Beth Manor Drive (Same Street)')
    w.placeholder('COMPS_TABLE')
    w.blank()

    w.h2('Equity Created at Completion')
    w.placeholder('EQUITY_TABLE')
    w.blank()

    w.h2('Capital Recovery at Refinance  (75% LTV)')
    w.placeholder('REFI_TABLE')
    w.blank()
    w.p('The conventional refinance returned more than 100% of deployed capital — '
        'all $120,000 back, plus $6,750 surplus. This is the BRRR model working exactly as designed.',
        bold=True, color=TEAL, sa=4, sb=8)

    w.h2('Monthly Cash Flow (Post-Refinance)')
    w.p('The property rents for $1,600/month. After PITI and property management, '
        'this deal nets $482/month in positive cash flow — in addition to the $49,000 '
        'in equity already created and all capital recovered at refinance.',
        sa=0, sb=8)
    w.placeholder('CASHFLOW_TABLE')
    w.blank()
    w.rule()

    # Terms
    w.h1('YOUR INVESTMENT TERMS')
    w.placeholder('TERMS_TABLE')
    w.blank()

    w.h2('What 8% Looks Like in Real Dollars')
    w.placeholder('RETURNS_TABLE')
    w.blank()

    w.h2('How Your Capital Works Over 2 Years')
    w.p('Your capital funds Deal #1. The refinance returns all principal within 6–9 months. '
        'That capital immediately funds Deal #2. The cycle repeats. Throughout the entire '
        'period you earn 8% annually on your outstanding balance — whether the capital is '
        'in Deal #1, Deal #2, or Deal #3.', sa=0, sb=7)
    w.p('Over 24 months, your money may cycle through 3–4 acquisitions, each building '
        'equity, each returning capital, each generating rental income.',
        sa=0, sb=8)
    w.rule()

    # Capital Protection
    w.h1('CAPITAL PROTECTION')
    w.p('Your investment is protected at multiple levels:', sa=0, sb=8)
    w.h3('1.  Conservative Underwriting')
    w.p('Every deal must produce a minimum 25% equity position before capital is committed. '
        'Deals that do not meet this threshold are declined — no exceptions.', sa=2, sb=8)
    w.h3('2.  Independent Appraisal Before Every Purchase')
    w.p('Our licensed appraiser performs a full CMA before any offer. The same appraiser '
        'supports the conventional refinance — no gap between purchase valuation and bank valuation.',
        sa=2, sb=8)
    w.h3('3.  Promissory Note')
    w.p('All lending is formalized with a signed promissory note specifying loan amount, '
        'interest rate, term, and repayment obligations. This is a legal, enforceable agreement.',
        sa=2, sb=8)
    w.h3('4.  Optional Deed of Trust')
    w.p('At your option, we record a deed of trust against each property, giving you a '
        'secured lien position backed by real property with a 25–29% equity buffer.',
        sa=2, sb=8)
    w.h3('5.  Equity Cushion at Refinance')
    w.p('After the conventional refinance we hold only 75% LTV. The property must decline '
        '25% in value before your security is compromised. Montgomery has not experienced '
        'that level of correction in any recorded period.', sa=2, sb=8)
    w.rule()

    # Track Record
    w.h1('TRACK RECORD')
    w.placeholder('TRACK_TABLE')
    w.blank()
    w.rule()

    # Summary
    w.h1('SUMMARY: WHAT YOU GET')
    w.bullet('8% annual guaranteed return — contractual, not projected')
    w.bullet('$24,000 guaranteed over the 2-year minimum term (on $150,000)')
    w.bullet('Capital secured by real property with 25–29% equity cushion')
    w.bullet('Proven deal model — 5 acquisitions completed since November 2025')
    w.bullet('Independent appraisal before every acquisition — no guesswork on value')
    w.bullet('Full transparency: every deal, every appraisal, every refinance statement')
    w.bullet('Optional deed of trust for maximum security')
    w.blank()
    w.rule()

    # Next Steps
    w.h1('NEXT STEPS')
    w.p('I would welcome a conversation to walk through any of the numbers above in detail, '
        'review the actual appraisals and closing documents from completed deals, and structure '
        'the lending agreement in whatever format gives you the most confidence.',
        sa=0, sb=8)
    w.p('The goal is a partnership built on verified numbers, clear documentation, and mutual trust.',
        bold=True, sa=0, sb=14)
    w.blank()
    w.p('[Your Name]  |  [Phone Number]  |  [Email]',
        bold=True, color=NAVY, fs=13, align='CENTER', sa=4, sb=4)
    w.blank()
    w.blank()
    w.p('All projections are based on actual completed acquisitions. '
        'The 8% annual return is a contractual guarantee, not dependent on individual property performance.',
        italic=True, color=rgb(140,140,140), fs=9, sa=10, sb=4)

    batch(svc, w.reqs)
    print("Text inserted.")


# ── Table data ─────────────────────────────────────────────────────────────────
TABLES = {
    'DEAL_SUMMARY': (
        ['Item', 'Amount'],
        [['Purchase Price', '$80,000'],
         ['Rehab Budget', '$40,000'],
         ['Total Capital Deployed (All-In)', '$120,000'],
         ['After-Repair Value (Appraised ARV)', '$169,000']]
    ),
    'COMPS_TABLE': (
        ['Address', 'Beds / Baths', 'Sale Price', 'Date'],
        [['1155 Beth Manor Dr', '4 BD / 2 BA', '$174,500', 'Aug 2023'],
         ['1148 Beth Manor Dr', '3 BD / 1 BA', '$77,000',  'Feb 2023'],
         ['1118 Beth Manor Dr', '—',            '$80,000',  'Apr 2021']]
    ),
    'EQUITY_TABLE': (
        ['Item', 'Amount'],
        [['After-Repair Value (Appraised)', '$169,000'],
         ['Total Capital Invested', '$120,000'],
         ['Equity Created at Completion', '$49,000'],
         ['Equity as % of Property Value', '29%']]
    ),
    'REFI_TABLE': (
        ['Item', 'Amount'],
        [['Appraised Value (ARV)', '$169,000'],
         ['Refinance Loan-to-Value', '75%'],
         ['Conventional Loan Amount', '$126,750'],
         ['Total Capital Originally Deployed', '$120,000'],
         ['Cash Returned to Lender at Refi', '$126,750'],
         ['Net Cash-Out Above Deployment', '+$6,750']]
    ),
    'CASHFLOW_TABLE': (
        ['Monthly Item', '$120K All-In Deal', '$150K All-In Deal'],
        [['Gross Rent', '$1,600', '$1,850'],
         ['Property Management (10%)', '– $160', '– $185'],
         ['PITI (Principal, Interest, Taxes, Insurance)', '– $958', '– $1,100 (est.)'],
         ['Net Monthly Cash Flow', '$482 / month', '$565 / month'],
         ['Annual Cash Flow', '$5,784', '$6,780']]
    ),
    'TERMS_TABLE': (
        ['Term', 'Detail'],
        [['Loan Amount', '$120,000 – $150,000'],
         ['Annual Interest Rate', '8% Guaranteed'],
         ['Minimum Term', '2 Years'],
         ['Payment Options', 'Monthly interest payments or lump sum at maturity'],
         ['Principal Return', 'Returned in full at end of term'],
         ['Security', 'Promissory Note  +  Optional Deed of Trust']]
    ),
    'RETURNS_TABLE': (
        ['Loan Amount', 'Annual Return', '2-Year Guaranteed Return', 'Monthly Payment'],
        [['$120,000', '$9,600',  '$19,200', '$800 / month'],
         ['$135,000', '$10,800', '$21,600', '$900 / month'],
         ['$150,000', '$12,000', '$24,000', '$1,000 / month']]
    ),
    'TRACK_TABLE': (
        ['Metric', 'Status'],
        [['Active Montgomery acquisitions since Nov 2025', '5 Properties Closed'],
         ['Strategy', 'BRRR (Buy, Rehab, Rent, Refinance, Repeat)'],
         ['Acquisition approach', 'Off-market, distressed sellers, below ARV'],
         ['Pre-purchase appraisal', 'Independent licensed appraiser — every deal'],
         ['Refinancing lender relationship', 'Conventional lender — same appraiser used']]
    ),
}

# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    svc = get_svc()
    print("Clearing document...")
    clear_doc(svc)
    print("Inserting text content...")
    build_text(svc)
    print("Inserting tables...")
    for name, (headers, rows) in TABLES.items():
        insert_table(svc, name, headers, rows)
    print(f"\nDone! View at: https://docs.google.com/document/d/{DOC_ID}/edit")

if __name__ == '__main__':
    main()
