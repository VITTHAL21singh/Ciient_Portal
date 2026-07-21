import os
from functools import wraps
import resend
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from prisma import Prisma
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-only-change-me")

db = Prisma()
db.connect()

STAGES = ["Discovery", "Design", "Development", "Review", "Delivered"]


# ---------- Auth helpers ----------
def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin_id"):
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)
    return wrapped

def client_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("client_id"):
            return redirect(url_for("client_login"))
        return view(*args, **kwargs)
    return wrapped

def freelancer_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("freelancer_id"):
            return redirect(url_for("freelancer_login"))
        return view(*args, **kwargs)
    return wrapped

# ---------- Public / root ----------
@app.route("/")
def index():
    if session.get("admin_id"):
        return redirect(url_for("admin_dashboard"))
    if session.get("client_id"):
        return redirect(url_for("client_portal"))
    return redirect(url_for("client_login"))


# ---------- Client-facing login + portal ----------
@app.route("/login", methods=["GET", "POST"])
def client_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        client = db.client.find_unique(where={"email": email})
        if client and check_password_hash(client.passwordHash, password):
            session.clear()
            session["client_id"] = client.id
            return redirect(url_for("client_portal"))

        flash("That email or password doesn't match our records.")
    return render_template("client_login.html")

@app.route("/portal")
@client_required
def client_portal():
    client = db.client.find_unique(
        where={"id": session["client_id"]},
        include={"projects": {"include": {"updates": True, "tasks": True, "events": True, "deliverables": True}}},
    )
    if not client:
        session.clear()
        return redirect(url_for("client_login"))

    for project in client.projects:
        project.events.sort(key=lambda e: e.eventDate)
        project.updates.sort(key=lambda u: u.createdAt, reverse=True)

    return render_template("client_portal.html", client=client, stages=STAGES)

@app.route("/portal/projects/<project_id>/upload", methods=["POST"])
@client_required
def client_upload(project_id):
    file_name = request.form.get("file_name", "").strip()
    file_url = request.form.get("file_url", "").strip()
    
    if file_name and file_url:
        db.deliverable.create(data={
            "uploaded_by_role": "Client",
            "file_name": file_name,
            "file_path_or_url": file_url,
            "is_released_to_client": True, 
            "projectId": project_id
        })
        
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = "Client Upload Received"
            msg["From"] = "portal@youragency.com"
            msg["To"] = "admin@youragency.com" 

            html_content = "<h3>New client onboarding data has been received.</h3>"
            msg.attach(MIMEText(html_content, "html"))

            with smtplib.SMTP("sandbox.smtp.mailtrap.io", 2525) as server:
                server.login("0c598969ef9878", "059aa284948357")
                server.sendmail(msg["From"], msg["To"], msg.as_string())
        except Exception as e:
            print(f"Failed to send Admin notification: {e}")

        flash("Asset uploaded successfully.")
    return redirect(url_for("client_portal"))

@app.route("/logout")
def client_logout():
    session.pop("client_id", None)
    return redirect(url_for("client_login"))


# ---------- Freelancer login ----------
@app.route("/freelancer/login", methods=["GET", "POST"])
def freelancer_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        freelancer = db.freelancer.find_unique(where={"email": email})
        if freelancer and check_password_hash(freelancer.passwordHash, password):
            session.clear()
            session["freelancer_id"] = freelancer.id
            return redirect(url_for("freelancer_portal"))

        flash("That email or password doesn't match our records.")
    return render_template("freelancer_login.html")

@app.route("/freelancer/portal")
@freelancer_required
def freelancer_portal():
    freelancer = db.freelancer.find_unique(
        where={"id": session["freelancer_id"]},
        include={"projects": {"include": {"deliverables": True, "updates": True}}}
    )
    if not freelancer:
        session.clear()
        return redirect(url_for("freelancer_login"))
        
    return render_template("freelancer_portal.html", freelancer=freelancer)

@app.route("/freelancer/logout")
def freelancer_logout():
    session.pop("freelancer_id", None)
    return redirect(url_for("freelancer_login"))


# ---------- Admin login ----------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        admin = db.admin.find_unique(where={"email": email})
        if admin and check_password_hash(admin.passwordHash, password):
            session.clear()
            session["admin_id"] = admin.id
            return redirect(url_for("admin_dashboard"))

        flash("That email or password doesn't match our records.")
    return render_template("admin_login.html")

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_id", None)
    return redirect(url_for("admin_login"))


# ---------- Admin Separated Dashboard Pages ----------

# 1. Main Dashboard (Active Pipeline)
# ---------- Admin dashboard (UPDATED TO PASS active_page) ----------
@app.route("/admin")
@admin_required
def admin_dashboard():
    clients = db.client.find_many(
        include={"projects": {"include": {"freelancer": True}}}, order={"createdAt": "desc"}
    )
    all_events = db.event.find_many(
        include={"project": {"include": {"client": True}}},
        order={"eventDate": "asc"}
    )
    freelancers = db.freelancer.find_many()
    
    # Notice the active_page="active" added at the end here
    return render_template("admin_dashboard.html", clients=clients, all_events=all_events, freelancers=freelancers, active_page="active")

# ---------- NEW SEPARATE PAGE ROUTES (ADD THESE BELOW) ----------

@app.route("/admin/projects")
@admin_required
def admin_projects():
    projects = db.project.find_many(include={"client": True, "freelancer": True})
    return render_template("admin_projects.html", projects=projects, active_page="projects")

@app.route("/admin/clients")
@admin_required
def admin_clients_page():
    clients = db.client.find_many()
    return render_template("admin_clients.html", clients=clients, active_page="client")

@app.route("/admin/roster")
@admin_required
def admin_roster():
    freelancers = db.freelancer.find_many()
    return render_template("admin_roster.html", freelancers=freelancers, active_page="roster")

@app.route("/admin/assets")
@admin_required
def admin_assets():
    # Grabs ALL files across the entire agency
    assets = db.deliverable.find_many(include={"project": {"include": {"client": True}}})
    return render_template("admin_assets.html", assets=assets, active_page="asset")

@app.route("/admin/approvals")
@admin_required
def admin_approvals():
    # Grabs ONLY files that have NOT been released to the client yet
    pending_approvals = db.deliverable.find_many(
        where={"is_released_to_client": False},
        include={"project": {"include": {"client": True}}}
    )
    return render_template("admin_approvals.html", approvals=pending_approvals, active_page="approvals")
# ---------- Admin Creation Routes ----------

@app.route("/admin/clients/new", methods=["GET", "POST"])
@admin_required
def new_client():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        tier = request.form.get("package_tier", "Module 1")

        if not name or not email or not password:
            flash("Please fill in every field.")
            return render_template("client_new.html")

        existing = db.client.find_unique(where={"email": email})
        if existing:
            flash("A client with that email already exists.")
            return render_template("client_new.html")

        db.client.create(
            data={
                "name": name,
                "email": email,
                "passwordHash": generate_password_hash(password),
                "package_tier": tier
            }
        )
        flash(f"{name} has been added. Share their email and password so they can log in.")
        return redirect(url_for("admin_dashboard"))

    return render_template("client_new.html")


@app.route("/admin/freelancers/new", methods=["GET", "POST"])
@admin_required
def new_freelancer():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        specialization = request.form.get("specialization", "Visual Architect")

        if not name or not email or not password:
            flash("Please fill in every field.")
            return render_template("freelancer_new.html")
            
        existing = db.freelancer.find_unique(where={"email": email})
        if existing:
            flash("A freelancer with that email already exists.")
            return render_template("freelancer_new.html")

        db.freelancer.create(
            data={
                "name": name,
                "email": email,
                "passwordHash": generate_password_hash(password),
                "specialization": specialization
            }
        )
        flash(f"Freelancer {name} added successfully.")
        return redirect(url_for("admin_dashboard"))
        
    return render_template("freelancer_new.html")


@app.route("/admin/clients/<client_id>/projects/new", methods=["GET", "POST"])
@admin_required
def new_project(client_id):
    client = db.client.find_unique(where={"id": client_id})
    freelancers = db.freelancer.find_many()
    
    if not client:
        flash("Client not found.")
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        code_name = request.form.get("code_name", "").strip()
        freelancer_id = request.form.get("freelancer_id", "")

        if not name:
            flash("Please give the project a name.")
            return render_template("project_new.html", client=client, freelancers=freelancers)

        project_data = {
            "name": name,
            "project_code_name": code_name,
            "clientId": client.id
        }
        
        if freelancer_id:
            project_data["freelancerId"] = freelancer_id

        project = db.project.create(data=project_data)
        return redirect(url_for("project_detail", project_id=project.id))

    return render_template("project_new.html", client=client, freelancers=freelancers)


# ---------- Project Management ----------
@app.route("/admin/projects/<project_id>")
@admin_required
def project_detail(project_id):
    project = db.project.find_unique(
        where={"id": project_id}, 
        include={"client": True, "updates": True, "tasks": True, "events": True, "deliverables": True} 
    )
    if not project:
        flash("Project not found.")
        return redirect(url_for("admin_dashboard"))

    project.events.sort(key=lambda e: e.eventDate)
    project.updates.sort(key=lambda u: u.createdAt, reverse=True)
    return render_template("project_detail_admin.html", project=project, stages=STAGES)


@app.route("/admin/projects/<project_id>/stage", methods=["POST"])
@admin_required
def update_stage(project_id):
    stage = request.form.get("stage")
    progress = request.form.get("progress", type=int, default=0)
    progress = max(0, min(100, progress))

    if stage in STAGES:
        db.project.update(
            where={"id": project_id}, data={"stage": stage, "progress": progress}
        )
        flash("Project status updated.")
    return redirect(url_for("project_detail", project_id=project_id))


@app.route("/admin/projects/<project_id>/updates/new", methods=["POST"])
@admin_required
def new_update(project_id):
    title = request.form.get("title", "").strip()
    body = request.form.get("body", "").strip()

    if title and body:
        db.update.create(data={"title": title, "body": body, "projectId": project_id})
        project = db.project.find_unique(
            where={"id": project_id}, 
            include={"client": True}
        )
        
        if project and project.client:
            try:
                msg = MIMEMultipart("alternative")
                msg["Subject"] = f"New Project Update: {project.name}"
                msg["From"] = "portal@youragency.com" 
                msg["To"] = project.client.email      

                html_content = f"""
                <div style="font-family: sans-serif; color: #1E2422;">
                    <h2 style="color: #1F4E4A;">New Update Posted</h2>
                    <p>Hi {project.client.name.split(' ')[0]},</p>
                    <p>A new status update has been added to your portal timeline:</p>
                    <div style="padding: 16px; border-left: 4px solid #1F4E4A; background: #F7F6F2; margin: 20px 0;">
                        <strong>{title}</strong><br>
                        <span style="color: #666F6C;">{body}</span>
                    </div>
                    <p><a href="http://localhost:5000/login" style="color: #1F4E4A; font-weight: bold;">Log in to your portal</a> to view the full details.</p>
                </div>
                """
                msg.attach(MIMEText(html_content, "html"))

                with smtplib.SMTP("sandbox.smtp.mailtrap.io", 2525) as server:
                    server.login("0c598969ef9878", "059aa284948357")
                    server.sendmail(msg["From"], msg["To"], msg.as_string())
                    
            except Exception as e:
                print(f"Failed to send via Mailtrap: {e}")

        flash("Update posted and client notified.")
    else:
        flash("Please add both a title and a message.")

    return redirect(url_for("project_detail", project_id=project_id))


@app.route("/admin/projects/<project_id>/events/new", methods=["POST"])
@admin_required
def new_event(project_id):
    title = request.form.get("title", "").strip()
    event_type = request.form.get("type", "Meeting")
    date_str = request.form.get("eventDate", "")
    description = request.form.get("description", "").strip()

    if title and date_str:
        try:
            parsed_date = datetime.strptime(date_str, "%Y-%m-%dT%H:%M")
            db.event.create(data={
                "title": title,
                "type": event_type,
                "eventDate": parsed_date,
                "description": description if description else None,
                "projectId": project_id
            })
            flash("Schedule event successfully locked in.")
        except ValueError:
            flash("Invalid date or time signature format.")
    else:
        flash("Event tracking requires both a title and a target timestamp.")

    return redirect(url_for("project_detail", project_id=project_id))


# ---------- Deliverables Vault & Magic Toggle ----------

@app.route("/projects/<project_id>/deliverables/new", methods=["POST"])
def submit_deliverable(project_id):
    if not session.get("freelancer_id") and not session.get("admin_id"):
        return redirect(url_for("index"))

    file_name = request.form.get("file_name", "").strip()
    file_url = request.form.get("file_url", "").strip()
    role = "Freelancer" if session.get("freelancer_id") else "Admin"

    if file_name and file_url:
        db.deliverable.create(data={
            "uploaded_by_role": role,
            "file_name": file_name,
            "file_path_or_url": file_url,
            "is_released_to_client": False,
            "projectId": project_id
        })

        if role == "Freelancer":
            db.project.update(
                where={"id": project_id},
                data={"current_status": "Admin Review"}
            )
            
            project = db.project.find_unique(where={"id": project_id})
            try:
                msg = MIMEMultipart("alternative")
                msg["Subject"] = f"Draft Ready for Review: {project.name}"
                msg["From"] = "portal@youragency.com"
                msg["To"] = "admin@youragency.com"

                html_content = f"<h3>Project {project.project_code_name or project.name} has file inputs ready for quality review.</h3>"
                msg.attach(MIMEText(html_content, "html"))

                with smtplib.SMTP("sandbox.smtp.mailtrap.io", 2525) as server:
                    server.login("0c598969ef9878", "059aa284948357")
                    server.sendmail(msg["From"], msg["To"], msg.as_string())
            except Exception as e:
                print(f"Failed to send Admin notification: {e}")

        flash("Asset successfully submitted to the Vault.")
    
    return redirect(request.referrer or url_for("index"))


@app.route("/admin/deliverables/<deliverable_id>/release", methods=["POST"])
@admin_required
def release_deliverable(deliverable_id):
    deliverable = db.deliverable.update(
        where={"id": deliverable_id},
        data={"is_released_to_client": True},
        include={"project": {"include": {"client": True}}}
    )

    if deliverable and deliverable.project and deliverable.project.client:
        client = deliverable.project.client
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = "Your Deliverables are Ready for Review"
            msg["From"] = "portal@youragency.com"
            msg["To"] = client.email

            html_content = f"""
            <div style="font-family: sans-serif; color: #1E2422;">
                <h2 style="color: #1F4E4A;">Deliverables Released</h2>
                <p>Hi {client.name.split(' ')[0]},</p>
                <p>Your custom strategic playbook deliverables are ready for review. Log into your dashboard to access your files.</p>
            </div>
            """
            msg.attach(MIMEText(html_content, "html"))

            with smtplib.SMTP("sandbox.smtp.mailtrap.io", 2525) as server:
                server.login("0c598969ef9878", "059aa284948357")
                server.sendmail(msg["From"], msg["To"], msg.as_string())
        except Exception as e:
            print(f"Failed to send Client notification: {e}")

    flash("Asset released to client view and client notified.")
    return redirect(url_for("project_detail", project_id=deliverable.projectId))


if __name__ == "__main__":
    app.run(debug=True)