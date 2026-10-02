# orchestrator.py - عقل النظام الموزع - Addoma Trading Services
import streamlit as st
from github import Github
import importlib.util
import os

GITHUB_TOKEN = st.secrets.get("github", {}).get("token") or os.environ.get("GITHUB_TOKEN")

def get_github_client():
    if not GITHUB_TOKEN:
        return None
    try:
        return Github(GITHUB_TOKEN)
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
    """المايسترو: حسب الحاجة يشغل المستودع المناسب تلقائيا"""
    need = need.lower()

    # خريطة الاحتياجات -> المستودعات
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
                # يشغل الكود في مساحة منفصلة ويرجع النتيجة
                local_vars = {}
                try:
                    exec(code, {}, local_vars)
                    return {"repo": repo, "code": code, "vars": local_vars, "status": "loaded"}
                except Exception as e:
                    return {"repo": repo, "error": str(e), "status": "error"}

    return {"status": "no_match", "need": need}

def list_my_repos():
    """يرجع كل مستودعاتك في GitHub"""
    g = get_github_client()
    if not g:
        return []
    try:
        return [r.name for r in g.get_user().get_repos() if not r.private or True][:50]
    except:
        return []

def sync_all_repos_to_app():
    """يجعل كل مستودعاتك تدعم بعضها"""
    repos = ["addoma-core", "addoma-dse-driver", "addoma-fuel-calc", "addoma-report-pdf", "addoma-iot-esp32"]
    results = {}
    for repo in repos:
        results[repo] = fetch_live_code(repo)
    return results
