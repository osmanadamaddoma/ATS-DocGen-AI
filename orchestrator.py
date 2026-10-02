# orchestrator.py - عقل النظام الموزع - Addoma Trading Services
import streamlit as st
import os

try:
    from github import Github
except ImportError:
    Github = None

def get_github_token():
    # يحاول يجيب التوكن من Secrets أو من Environment
    try:
        return st.secrets["github"]["token"]
    except:
        return os.environ.get("GITHUB_TOKEN")

def get_github_client():
    token = get_github_token()
    if not token or Github is None:
        return None
    try:
        return Github(token)
    except:
        return None

@st.cache_data(ttl=60)
def fetch_live_code(repo_name, file_path="main.py"):
    """يسحب آخر كود من أي مستودع في حسابك تلقائيا كل 60 ثانية"""
    g = get_github_client()
    if not g:
        return None
    try:
        user = g.get_user()
        repo = user.get_repo(repo_name)
        content = repo.get_contents(file_path)
        return content.decoded_content.decode()
    except Exception as e:
        print(f"Orchestrator fetch error {repo_name}: {e}")
        return None

def auto_orchestrator(need: str):
    """المايسترو: حسب الحاجة يشغل المستودع المناسب"""
    need = need.lower()
    routing = {
        "fuel": "addoma-fuel-calc",
        "وقود": "addoma-fuel-calc",
        "dse": "addoma-dse-driver",
        "rpm": "addoma-dse-driver",
        "modbus": "addoma-dse-driver",
        "pdf": "addoma-report-pdf",
        "تقرير": "addoma-report-pdf",
        "esp32": "addoma-iot-esp32",
        "iot": "addoma-iot-esp32",
        "cable": "addoma-cable-calc"
    }
    for keyword, repo in routing.items():
        if keyword in need:
            code = fetch_live_code(repo)
            if code:
                return {"repo": repo, "code": code, "status": "loaded"}
    return {"status": "no_match", "need": need}

def list_my_repos():
    g = get_github_client()
    if not g:
        return []
    try:
        return [r.name for r in g.get_user().get_repos()][:50]
    except:
        return []

def run_addoma_brain():
    st.sidebar.markdown("### 🧠 Addoma Brain")
    repos = list_my_repos()
    if repos:
        st.sidebar.success(f"متصل بـ {len(repos)} مستودع")
    else:
        st.sidebar.warning("أضف GITHUB_TOKEN في Secrets")
