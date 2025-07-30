from duckduckgo_search import DDGS  # Add this at the top (install with: pip install duckduckgo-search)
from flask import Flask, render_template, request, redirect, url_for, send_file, session
import re, io
from bs4 import BeautifulSoup
import requests
import pandas as pd
from openpyxl import Workbook

from flask import g

emails_storage = []


app = Flask(__name__)
app.secret_key = "email_extractor_secret"

EMAIL_REGEX = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'

def extract_emails_from_url(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        html = requests.get(url, timeout=5, headers=headers).text
        soup = BeautifulSoup(html, 'html.parser')
        emails = re.findall(EMAIL_REGEX, soup.get_text())
        return list(set(emails))
    except Exception:
        return []

def get_search_result_links(query):
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(f"https://www.google.com/search?q={query}", headers=headers)
    soup = BeautifulSoup(response.text, "html.parser")
    links = []
    for tag in soup.find_all("a"):
        href = tag.get("href")
        if href and "/url?q=" in href:
            url = href.split("/url?q=")[1].split("&")[0]
            if "google" not in url:
                links.append(url)
    return list(set(links))[:5]  # Limit to 5 for quick testing

@app.route("/")
def index():
    emails = session.pop("emails", [])
    searched = session.pop("searched", False)
    return render_template("index.html", emails=emails, searched=searched)

@app.route("/extract_manual", methods=["POST"])
def extract_manual():
    global emails_storage
    url = request.form.get("manual_url").strip()
    emails = extract_emails_from_url(url)
    result = [{"email": email, "source": url} for email in emails]
    session["emails"] = result
    session["searched"] = True
    emails_storage = result
    return redirect(url_for("index"))


@app.route("/extract_file", methods=["POST"])
def extract_file():
    global emails_storage
    file = request.files.get("file")
    if not file:
        session["emails"] = []
        session["searched"] = True
        emails_storage = []
        return redirect(url_for("index"))

    urls = []
    if file.filename.endswith(".txt"):
        content = file.read().decode()
        urls = content.splitlines()
    elif file.filename.endswith(".csv"):
        df = pd.read_csv(file)
        urls = df.iloc[:, 0].dropna().tolist()
    elif file.filename.endswith(".xlsx"):
        df = pd.read_excel(file)
        urls = df.iloc[:, 0].dropna().tolist()
    else:
        session["emails"] = []
        session["searched"] = True
        emails_storage = []
        return redirect(url_for("index"))

    result = []
    for url in urls:
        url = url.strip()
        if url:
            found_emails = extract_emails_from_url(url)
            for email in found_emails:
                result.append({"email": email, "source": url})

    session["emails"] = result
    session["searched"] = True
    emails_storage = result
    return redirect(url_for("index"))


    # result = []
    # for url in urls:
    #     url = url.strip()
    #     if url:
    #         found_emails = extract_emails_from_url(url)
    #         for email in found_emails:
    #             result.append({"email": email, "source": url})

    # session["emails"] = result
    # session["searched"] = True
    # emails_storage = result  # <-- this makes download work reliably
    # return redirect(url_for("index"))



@app.route("/extract_location", methods=["POST"])
def extract_location():
    service = request.form.get("service", "")
    country = request.form.get("country", "")
    city = request.form.get("city", "")

    query = f"{service} companies in {city} {country}"

    results = []
    try:
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=10):  # limit results for speed
                url = r.get("href") or r.get("url")
                if url:
                    found_emails = extract_emails_from_url(url)
                    for email in found_emails:
                        results.append({"email": email, "source": url})
    except Exception as e:
        print("Search error:", e)

    session["emails"] = results
    session["searched"] = True
    return redirect(url_for("index"))


@app.route("/download")
def download():
    global emails_storage
    if not emails_storage:
        return redirect(url_for("index"))

    output = io.BytesIO()
    wb = Workbook()
    ws = wb.active
    ws.append(["Email", "Website"])

    for item in emails_storage:
        ws.append([item["email"], item["source"]])

    wb.save(output)
    output.seek(0)

    return send_file(output, download_name="emails.xlsx", as_attachment=True)



if __name__ == "__main__":
    app.run(debug=True)
