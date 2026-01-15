import streamlit as st
import pandas as pd
import plotly.express as px
from io import BytesIO
from fpdf import FPDF
from datetime import datetime
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import urllib.parse
import sqlite3 # La mémoire du système

# ==========================================
# 1. CONFIGURATION & BASE DE DONNÉES
# ==========================================
st.set_page_config(
    page_title="KASHFLOW.AI",
    page_icon="🦅",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Fonction pour initialiser la base de données
def init_db():
    conn = sqlite3.connect('kashflow.db')
    c = conn.cursor()
    # On crée la table si elle n'existe pas
    c.execute('''CREATE TABLE IF NOT EXISTS logs
                 (date TEXT, utilisateur TEXT, action TEXT, cible TEXT)''')
    conn.commit()
    conn.close()

# On lance l'initialisation au démarrage
init_db()

def log_action(user, action, client):
    conn = sqlite3.connect('kashflow.db')
    c = conn.cursor()
    timestamp = datetime.now().strftime("%d/%m/%Y %H:%M")
    c.execute("INSERT INTO logs VALUES (?, ?, ?, ?)", (timestamp, user, action, client))
    conn.commit()
    conn.close()

def get_logs():
    conn = sqlite3.connect('kashflow.db')
    df = pd.read_sql_query("SELECT * FROM logs", conn)
    conn.close()
    return df

# ==========================================
# 2. MOTEUR DE CALCUL
# ==========================================
class KashflowEngine:
    def audit_portefeuille(self, df):
        col_map = {
            'Name': 'Client', 'Nom': 'Client', 'Customer': 'Client',
            'Due Date': 'Date_Echeance', 'Echeance': 'Date_Echeance',
            'Amount': 'Reste_A_Payer', 'Solde': 'Reste_A_Payer', 'Montant': 'Reste_A_Payer'
        }
        df = df.rename(columns=col_map)
        
        if 'Date_Echeance' in df.columns:
            df['Date_Echeance'] = pd.to_datetime(df['Date_Echeance'], errors='coerce')
        else:
            df['Date_Echeance'] = datetime.now()

        if 'Reste_A_Payer' in df.columns:
            df['Reste_A_Payer'] = pd.to_numeric(df['Reste_A_Payer'], errors='coerce').fillna(0)
        
        today = pd.Timestamp.now()
        df['Jours_Retard'] = (today - df['Date_Echeance']).dt.days
        df['Jours_Retard'] = df['Jours_Retard'].fillna(0).astype(int)

        def get_statut(retard):
            if retard < 0: return "✅ Sain"
            if retard < 30: return "⚠️ Retard Mineur"
            return "🔴 CRITIQUE"

        df['Statut'] = df['Jours_Retard'].apply(get_statut)

        kpis = {
            'total_dehors': df['Reste_A_Payer'].sum(),
            'total_critique': df[df['Statut'] == "🔴 CRITIQUE"]['Reste_A_Payer'].sum(),
            'nb_clients_danger': df[df['Statut'] == "🔴 CRITIQUE"]['Client'].nunique(),
            'retard_moyen': df[df['Jours_Retard'] > 0]['Jours_Retard'].mean()
        }
        if pd.isna(kpis['retard_moyen']): kpis['retard_moyen'] = 0

        return kpis, df

    def get_top_mauvais_payeurs(self, df):
        top = df.groupby('Client')['Reste_A_Payer'].sum().reset_index()
        top = top.sort_values(by='Reste_A_Payer', ascending=False).head(7)
        return top

engine = KashflowEngine()

# ==========================================
# 3. LOGIN
# ==========================================
def check_password():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        return True

    st.markdown("<style>.stApp { background-color: #0F172A; }</style>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        st.markdown("""
            <div style="text-align:center; padding-top:50px;">
                <div style="font-size: 60px;">🦅</div>
                <h1 style="color:white; margin:0;">KASHFLOW.AI</h1>
                <p style="color:#94A3B8;">Cloud Edition v9.0</p>
            </div>
        """, unsafe_allow_html=True)
        with st.form("login_form"):
            user = st.text_input("Identifiant", placeholder="admin")
            password = st.text_input("Mot de passe", type="password")
            if st.form_submit_button("CONNEXION", type="primary", use_container_width=True):
                if user == "admin" and password == "admin123":
                    st.session_state.authenticated = True
                    st.session_state.user = user
                    st.rerun()
                else:
                    st.error("Accès refusé.")
    return False

if not check_password():
    st.stop()

# ==========================================
# 4. DESIGN
# ==========================================
def load_design_system():
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
        html, body, [class*="css"] { font-family: 'Inter', sans-serif; color: #1E293B; }
        .stApp { background-color: #F8FAFC; background-image: radial-gradient(#E2E8F0 1px, transparent 1px); background-size: 24px 24px; }
        .metric-card { background: #FFFFFF; border-radius: 16px; padding: 24px; border: 1px solid #F1F5F9; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.02); }
        .kpi-label { font-size: 11px; font-weight: 700; text-transform: uppercase; color: #64748B; }
        .kpi-value { font-size: 28px; font-weight: 800; color: #0F172A; }
        .risk-gauge { height: 10px; background: #E2E8F0; border-radius: 5px; overflow: hidden; margin-top: 5px; }
        .risk-fill { height: 100%; border-radius: 5px; transition: width 0.5s ease; }
        header {visibility: hidden;} .block-container {padding-top: 2rem;}
        </style>
    """, unsafe_allow_html=True)

def metric_card(title, value, subtext, col, status="info"):
    colors = {"danger": "#FEE2E2", "success": "#DCFCE7", "warn": "#FEF3C7", "info": "#E0F2FE"}
    text_colors = {"danger": "#991B1B", "success": "#166534", "warn": "#92400E", "info": "#075985"}
    with col:
        st.markdown(f"""
        <div class="metric-card">
            <div class="kpi-label">{title}</div>
            <div class="kpi-value">{value}</div>
            <div style="margin-top:12px;">
                <span style="background:{colors[status]}; color:{text_colors[status]}; padding:4px 10px; border-radius:20px; font-size:11px; font-weight:700;">{subtext}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

load_design_system()

# --- EMAILS ---
def send_email_gmail(sender_email, sender_password, receiver_email, subject, body):
    try:
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = receiver_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, receiver_email, msg.as_string())
        server.quit()
        return True, "Email envoyé avec succès !"
    except Exception as e:
        return False, str(e)

# --- PDF ---
class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 15)
        self.cell(0, 10, 'KASHFLOW RECOUVREMENT', 0, 1, 'C')
        self.ln(10)

def generer_mise_en_demeure(client_name, df_client):
    pdf = PDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(0, 10, f"Date : {datetime.now().strftime('%d/%m/%Y')}", 0, 1, 'R')
    pdf.ln(10)
    pdf.set_font("Arial", 'B', size=12)
    pdf.cell(0, 10, f"À l'attention de : {client_name}", 0, 1, 'L')
    pdf.ln(10)
    pdf.set_font("Arial", 'B', size=16)
    pdf.set_text_color(220, 53, 69)
    pdf.cell(0, 10, "OBJET : MISE EN DEMEURE", 0, 1, 'C')
    pdf.set_text_color(0, 0, 0)
    pdf.ln(10)
    pdf.set_font("Arial", size=11)
    pdf.multi_cell(0, 8, "Sauf erreur de notre part, les factures ci-dessous restent impayees malgre nos relances.")
    pdf.ln(10)
    pdf.set_font("Arial", 'B', size=10)
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(80, 10, "Ref", 1, 0, 'C', 1)
    pdf.cell(50, 10, "Date", 1, 0, 'C', 1)
    pdf.cell(60, 10, "Montant", 1, 1, 'C', 1)
    pdf.set_font("Arial", size=10)
    total_du = 0
    for index, row in df_client.iterrows():
        ref = str(row.get('Reference', f"#{index}"))[:20]
        date = str(row.get('Date_Echeance', 'N/A'))[:10]
        montant = row.get('Reste_A_Payer', 0)
        total_du += montant
        pdf.cell(80, 10, ref, 1)
        pdf.cell(50, 10, date, 1, 0, 'C')
        pdf.cell(60, 10, f"{montant:,.0f}", 1, 1, 'R')
    pdf.set_font("Arial", 'B', size=12)
    pdf.cell(130, 10, "TOTAL :", 1, 0, 'R')
    pdf.cell(60, 10, f"{total_du:,.0f} FCFA", 1, 1, 'R')
    pdf.ln(20)
    pdf.set_font("Arial", size=11)
    pdf.multi_cell(0, 8, "Veuillez regulariser sous 8 jours.")
    pdf.ln(10)
    pdf.cell(0, 10, "Service Recouvrement", 0, 1, 'R')
    return pdf.output(dest='S').encode('latin-1', 'replace')

# ==========================================
# 5. SIDEBAR
# ==========================================
with st.sidebar:
    st.markdown("### 🦅 **KASHFLOW** .AI")
    
    with st.expander("⚙️ Config Email", expanded=False):
        my_email = st.text_input("Votre Gmail")
        my_password = st.text_input("Mdp Application", type="password")
    
    if st.button("🔒 Déconnexion"):
        st.session_state.authenticated = False
        st.rerun()
        
    st.markdown("---")
    uploaded_file = st.file_uploader("📂 Charger Grand Livre", type=['csv', 'xlsx'])
    
    df_source = None
    if uploaded_file is not None:
        try:
            uploaded_file.seek(0)
            if uploaded_file.name.endswith('.csv'):
                df_source = pd.read_csv(uploaded_file)
            else:
                df_source = pd.read_excel(uploaded_file)
            _, df_source_clean = engine.audit_portefeuille(df_source)
            if 'Client' in df_source_clean.columns:
                clients_uniques = sorted(df_source_clean['Client'].unique().tolist())
                st.success(f"✅ {len(clients_uniques)} Dossiers")
            else:
                st.error("Colonne 'Client' manquante")
                clients_uniques = []
        except Exception as e:
            st.error(f"Erreur Lecture: {e}")
            clients_uniques = []

        st.markdown("---")
        st.markdown("### 🎯 ACTION")
        client_selectionne = st.selectbox("Cible :", clients_uniques, index=None, placeholder="Chercher...", key="search")
        
        if client_selectionne:
            df_client = df_source_clean[df_source_clean['Client'] == client_selectionne]
            total_client = df_client['Reste_A_Payer'].sum()
            retard_max = df_client['Jours_Retard'].max() if 'Jours_Retard' in df_client.columns else 0
            risk_score = min(100, max(0, int(retard_max / 1.2)))
            
            if risk_score < 30: color, label = "#10B981", "Fiable"
            elif risk_score < 70: color, label = "#F59E0B", "Attention"
            else: color, label = "#EF4444", "CRITIQUE"

            st.markdown(f"""
                <div style="background:white; padding:15px; border-radius:10px; border:1px solid #E2E8F0; margin-bottom:15px;">
                    <div style="display:flex; justify-content:space-between; margin-bottom:5px;">
                        <span style="font-size:12px; font-weight:bold; color:#64748B;">RISQUE</span>
                        <span style="font-size:12px; font-weight:bold; color:{color};">{risk_score}% ({label})</span>
                    </div>
                    <div class="risk-gauge"><div class="risk-fill" style="width:{risk_score}%; background-color:{color};"></div></div>
                    <div style="margin-top:10px; font-size:18px; font-weight:800; color:#1E293B;">{total_client:,.0f} CFA</div>
                </div>
            """, unsafe_allow_html=True)
            
            tab_mail, tab_sms, tab_docs = st.tabs(["EMAIL", "WHATSAPP", "DOCS"])
            with tab_mail:
                target_email = st.text_input("Email client", placeholder="@")
                sujet = st.text_input("Sujet", value=f"Relance - {client_selectionne}")
                corps = st.text_area("Message", value=f"Bonjour, sauf erreur, solde dû: {total_client:,.0f} FCFA.", height=80)
                if st.button("ENVOYER 🚀", type="primary"):
                    if my_email and my_password and target_email:
                        ok, msg = send_email_gmail(my_email, my_password, target_email, sujet, corps)
                        if ok: 
                            st.success("Envoyé !")
                            log_action(st.session_state.user, "Email envoyé", client_selectionne)
                        else: st.error(msg)
                    else: st.error("Config incomplète")
            with tab_sms:
                phone = st.text_input("Numéro (237...)", placeholder="2376...")
                msg_wa = urllib.parse.quote(f"Bonjour {client_selectionne}, solde dû: {total_client:,.0f} FCFA. Merci.")
                if phone:
                    st.markdown(f'<a href="https://wa.me/{phone}?text={msg_wa}" target="_blank"><button style="background:#25D366;color:white;border:none;padding:8px;width:100%;border-radius:5px;">📱 OUVRIR WHATSAPP</button></a>', unsafe_allow_html=True)
                    if st.button("Confirmer Envoi"): log_action(st.session_state.user, "WhatsApp", client_selectionne)
            with tab_docs:
                csv_data = df_client.to_csv(index=False).encode('utf-8')
                st.download_button("📊 Excel", csv_data, f"{client_selectionne}.csv", "text/csv", on_click=log_action, args=(st.session_state.user, "Export Excel", client_selectionne))
                try:
                    pdf_data = generer_mise_en_demeure(client_selectionne, df_client)
                    st.download_button("🔥 PDF Demeure", pdf_data, f"Relance_{client_selectionne}.pdf", "application/pdf", type="primary", on_click=log_action, args=(st.session_state.user, "PDF", client_selectionne))
                except Exception as e: st.error(f"Err PDF: {e}")

# ==========================================
# 6. DASHBOARD
# ==========================================
if uploaded_file and df_source is not None:
    try:
        kpis, df_traite = engine.audit_portefeuille(df_source)
    except Exception as e:
        st.error(f"Erreur Calcul: {e}")
        st.stop()

    tab1, tab2 = st.tabs(["📊 VUE D'ENSEMBLE", "📝 JOURNAL (PERSISTANT)"])

    with tab1:
        st.markdown("## Tableau de Bord Financier")
        c1, c2, c3, c4 = st.columns(4)
        metric_card("Trésorerie Dehors", f"{kpis['total_dehors']:,.0f}", "FCFA", c1, "info")
        metric_card("Montant Critique", f"{kpis['total_critique']:,.0f}", "FCFA", c2, "danger" if kpis['total_critique']>0 else "success")
        metric_card("Clients Risque", f"{kpis['nb_clients_danger']}", "Dossiers", c3, "warn")
        metric_card("DSO Moyen", f"{kpis['retard_moyen']:.0f}", "Jours", c4, "success")
        
        st.markdown("<br>", unsafe_allow_html=True)
        col_main, col_side = st.columns([2, 1])
        with col_main:
            st.markdown("### 🎯 Top Débiteurs")
            st.markdown('<div class="metric-card">', unsafe_allow_html=True)
            top_mauvais = engine.get_top_mauvais_payeurs(df_traite)
            fig = px.bar(top_mauvais, x='Reste_A_Payer', y='Client', orientation='h', text='Reste_A_Payer', color='Reste_A_Payer', color_continuous_scale=['#FF8A80', '#D32F2F'])
            fig.update_layout(template="plotly_white", yaxis={'categoryorder':'total ascending'}, xaxis=dict(showgrid=False), height=350, margin=dict(l=0, r=0, t=0, b=0))
            st.plotly_chart(fig, use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)
        with col_side:
            st.markdown("### ⚖️ Santé")
            st.markdown('<div class="metric-card">', unsafe_allow_html=True)
            repartition = df_traite.groupby('Statut')['Reste_A_Payer'].sum().reset_index()
            fig_pie = px.pie(repartition, values='Reste_A_Payer', names='Statut', color='Statut', color_discrete_map={'✅ Sain':'#10B981', '⚠️ Retard Mineur':'#F59E0B', '🔴 CRITIQUE':'#EF4444'}, hole=0.7)
            fig_pie.update_layout(template="plotly_white", showlegend=True, legend=dict(orientation="h", y=-0.2), margin=dict(l=0, r=0, t=0, b=0), height=300)
            st.plotly_chart(fig_pie, use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)

        st.markdown("<div style='height: 30px'></div>", unsafe_allow_html=True)
        st.markdown("### 📋 Tableau Global")
        st.dataframe(
            df_traite[['Client', 'Date_Echeance', 'Reste_A_Payer', 'Jours_Retard', 'Statut']].style.background_gradient(cmap='Reds', subset=['Jours_Retard']),
            use_container_width=True,
            column_config={"Reste_A_Payer": st.column_config.NumberColumn("Montant", format="%d FCFA")}
        )

    with tab2:
        st.markdown("## 📝 Historique Complet")
        st.caption("Ces données sont stockées dans la base de données locale (kashflow.db).")
        # On lit depuis la base de données
        try:
            df_logs = get_logs().iloc[::-1] # Inverse pour voir les récents en haut
            st.dataframe(df_logs, use_container_width=True, hide_index=True)
        except:
            st.info("Base de données vide.")
else:
    st.markdown("<div style='height: 100px'></div>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        st.markdown("""<div class="metric-card" style="text-align:center; padding:40px;"><div style="font-size: 50px;">🦅</div><h2 style="color:#1E293B;">KASHFLOW.AI</h2><p style="color:#64748B;">Base de données active.</p></div>""", unsafe_allow_html=True)