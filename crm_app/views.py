from datetime import date, datetime, timedelta
import io
import json
from typing import Optional

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q, F, Count, Avg, DurationField, ExpressionWrapper
from django.db.models.functions import TruncMonth, TruncDate
from django.http import (
    HttpResponse,
    FileResponse,
    HttpResponseBadRequest,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .forms import (
    LoginForm,
    ChecklistJSONUploadForm,
    ChecklistItemUpdateForm,
    CoordinationDeploymentForm,
    ProjectForm,
)

from .models import (
    ChecklistItem,
    Project,
    Technician,
    TimelineEntry,
    ChecklistItemImage,
    ChecklistItemNote,
)

User = get_user_model()

# --------------------------------


@login_required
def coordination_form_view(request):
    """
    Standalone route for the first-step 'Coordination & Déploiement' page.
    Only managers / planification counselors can access it.
    """
    tech = _sync_user_and_technician_from_directory(request.user)
    # Only allow managers or planification counselors
    if not _is_planner_or_manager_from_tech(tech):
        # You can use PermissionDenied to show 403, or redirect to the normal create page.
        # raise PermissionDenied("Accès réservé à la planification / gestion.")
        return redirect("project_create")

    if request.method == "POST":
        form = CoordinationDeploymentForm(request.POST, request.FILES)

        client_choices = [
            (name, name)
            for name in Project.objects.values_list("client_name", flat=True)
            .distinct()
            .order_by("client_name")
            if name
        ]
        form.fields["client_name"].choices = client_choices

        if form.is_valid():
            pn = form.cleaned_data["project_number"].strip()
            tgt_tech = form.cleaned_data["technician"]
            img = form.cleaned_data.get("coordination_board")
            client_name = form.cleaned_data["client_name"]

            # Create minimal project; the deployment specialist will complete details later.
            p = Project.objects.create(
                project_number=pn,
                environment="test",  # default, can be changed later
                client_name=client_name,
                product="",
                work_type="Migration",
                created_by=request.user,
                technician=tgt_tech,
                assigned_to=tgt_tech.user if tgt_tech else None,
                status="assigned",
                title=f"Coordination — {pn}",
            )

            # Save the selected project manager's name
            p.gestionnaire_projet = form.cleaned_data.get("gestionnaire_projet", "")

            # Planning windows + uploaded board
            p.prep_date = form.cleaned_data.get("prep_date")
            p.prep_start_time = form.cleaned_data.get("prep_start_time")
            p.prep_end_time = form.cleaned_data.get("prep_end_time")
            p.prod_date = form.cleaned_data.get("prod_date")
            p.prod_start_time = form.cleaned_data.get("prod_start_time")
            p.prod_end_time = form.cleaned_data.get("prod_end_time")
            if img:
                p.coordination_board = img
            p.save()

            messages.success(request, "Projet créé et assigné au technicien.")
            return redirect("project_detail", pk=p.pk)
    else:
        form = CoordinationDeploymentForm()
        client_choices = [
            (name, name)
            for name in Project.objects.values_list("client_name", flat=True)
            .distinct()
            .order_by("client_name")
            if name
        ]
        form.fields["client_name"].choices = client_choices

    return render(request, "coordination_form.html", {"form": form, "technician": tech})


@login_required
@require_POST
@csrf_exempt
def project_wizard_save(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    project_number = data.get("projet")
    if not project_number:
        return JsonResponse({"error": "Project number is required"}, status=400)

    project, created = Project.objects.get_or_create(
        project_number=project_number,
        defaults={
            "created_by": request.user,
            "technician": _sync_user_and_technician_from_directory(request.user),
        },
    )

    project.environment = data.get("env", project.environment)
    project.client_name = data.get("client", project.client_name)
    project.product = data.get("produit", project.product)
    project.date = data.get("date") or project.date
    project.database_name = data.get("nomBD", project.database_name)
    project.db_server = data.get("serveurBD", project.db_server)
    project.app_server = data.get("serveurApp", project.app_server)
    project.work_type = data.get("typeTravaux", project.work_type)

    technician_name = data.get("technicien")
    if technician_name:
        # This is a simplified lookup. A more robust solution would handle name conflicts.
        technician_user = User.objects.filter(
            first_name__iexact=technician_name.split(" ")[0]
        ).first()
        if technician_user:
            project.technician, _ = Technician.objects.get_or_create(
                user=technician_user
            )

    project.sre_name = data.get("sreName", project.sre_name)
    project.sre_phone = data.get("srePhone", project.sre_phone)
    project.fuse_validation = data.get("valFuse", project.fuse_validation)
    project.certificate_validation = data.get("valCert", project.certificate_validation)

    # Storing checklist and timeline data as JSON
    project.checklist_data = {"checks": data.get("checks")}
    # project.timeline_data = {"timeline": data.get("timeline"), "timelineExtras": data.get("timelineExtras")}

    project.save()

    return JsonResponse(
        {"message": "Project saved successfully", "projectId": project.pk}
    )


# Helpers for team directory/roles
# --------------------------------
def _directory_entry_for(email: str) -> dict | None:
    if not email:
        return None
    directory = getattr(settings, "TEAM_DIRECTORY", {}) or {}
    return directory.get(email.lower())


# --- Role helpers that accept a *User* ---
def _dir_entry_for_user(user):
    email = (getattr(user, "email", "") or "").lower()
    return (getattr(settings, "TEAM_DIRECTORY", {}) or {}).get(email, {})


def user_is_manager(user) -> bool:
    entry = _dir_entry_for_user(user)
    return bool(entry.get("is_manager", False))


def user_is_planification(user) -> bool:
    role = (_dir_entry_for_user(user).get("role") or "").lower()
    return "conseiller" in role and "planification" in role


def user_is_deployment_specialist(user) -> bool:
    role = (_dir_entry_for_user(user).get("role") or "").lower()
    return ("spécialis" in role) or ("deploiement" in role) or ("déploiement" in role)


def _sync_user_and_technician_from_directory(
    user: Optional[User],
) -> Optional[Technician]:
    """
    Ensure the User (names) and Technician (role/is_manager) reflect TEAM_DIRECTORY.
    If user is anonymous, return None. If no directory entry, keep existing values (role defaults to 'Technicien').
    """
    if not getattr(user, "is_authenticated", False):
        return None

    entry = _directory_entry_for(user.email)
    defaults_role = (entry or {}).get("role") or "Technicien"
    tech, _ = Technician.objects.get_or_create(
        user=user, defaults={"role": defaults_role}
    )

    if entry:
        changed = False
        if entry.get("first_name") and user.first_name != entry["first_name"]:
            user.first_name = entry["first_name"]
            changed = True
        if entry.get("last_name") and user.last_name != entry["last_name"]:
            user.last_name = entry["last_name"]
            changed = True
        if changed:
            user.save(update_fields=["first_name", "last_name"])

        if entry.get("role") and tech.role != entry["role"]:
            tech.role = entry["role"]
            tech.save(update_fields=["role"])

        if hasattr(tech, "is_manager"):
            is_mgr = bool(entry.get("is_manager", False))
            if tech.is_manager != is_mgr:
                tech.is_manager = is_mgr
                tech.save(update_fields=["is_manager"])

    return tech


def _normalize_email_for_lookup(raw: str) -> list[str]:
    """
    Accepts:
      - full email (any domain)
      - or just 'firstname.lastname' (no domain)
    Returns a small list of candidate emails to try.
    """
    e = (raw or "").strip()
    if not e:
        return []
    candidates: list[str] = []

    if "@" in e:
        candidates.append(e)
        local, domain = e.split("@", 1)
        if domain.lower() == "logibec.com":
            candidates.append(f"{local}@lgisolutions.com")
        elif domain.lower() == "lgisolutions.com":
            candidates.append(f"{local}@logibec.com")
    else:
        candidates.append(f"{e}@lgisolutions.com")
        candidates.append(f"{e}@logibec.com")

    out, seen = [], set()
    for c in candidates:
        c2 = c.lower()
        if c2 not in seen:
            out.append(c2)
            seen.add(c2)
    return out


def _is_planner_or_manager_from_tech(tech: Optional[Technician]) -> bool:
    """
    True if the technician is a manager or has a role containing 'planification'
    (case-insensitive, French/English variants).
    """
    if not tech:
        return False
    if getattr(tech, "is_manager", False):
        return True
    role = (tech.role or "").lower()
    return "planification" in role or "planner" in role or "conseiller" in role


# ------------------ Auth ------------------
def login_view(request):
    if request.user.is_authenticated:
        return redirect("home")

    form = LoginForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"].strip()
        password = form.cleaned_data["password"]
        user = authenticate(request, username=email, password=password)
        if user:
            login(request, user)
            messages.success(request, "Connexion réussie.")
            return redirect("home")
        else:
            messages.error(request, "E-mail ou mot de passe invalide.")
    return render(request, "login.html", {"form": form})


@login_required
def logout_view(request):
    logout(request)
    return redirect("login")


# ------------------ Dashboard ------------------
@login_required
def home_view(request):
    tech = _sync_user_and_technician_from_directory(request.user)
    is_manager = getattr(tech, "is_manager", False)
    projects = (
        Project.objects.all() if is_manager else Project.objects.filter(technician=tech)
    )

    total_projects = projects.count()
    pending_projects = projects.filter(status="pending").count()
    in_progress_projects = projects.filter(status="in_progress").count()
    completed_projects = projects.filter(status="completed").count()

    now = timezone.now()
    today = now.date()
    week_start = today - timedelta(days=today.weekday())
    prev_week_start = week_start - timedelta(days=7)
    prev_week_end = week_start

    new_this_week = projects.filter(created_at__date__gte=week_start).count()
    new_prev_week = projects.filter(
        created_at__date__gte=prev_week_start, created_at__date__lt=prev_week_end
    ).count()

    def _pct_change(current: int, prev: int) -> float:
        if prev == 0:
            return 100.0 if current > 0 else 0.0
        return round((current - prev) * 100.0 / prev, 1)

    total_trend_pct = _pct_change(new_this_week, new_prev_week)

    pending_new_today = projects.filter(
        status="pending", created_at__date=today
    ).count()
    pending_this_week = projects.filter(
        status="pending", created_at__date__gte=week_start
    ).count()
    pending_last_week = projects.filter(
        status="pending",
        created_at__date__gte=prev_week_start,
        created_at__date__lt=prev_week_end,
    ).count()
    pending_trend_pct = _pct_change(pending_this_week, pending_last_week)

    overdue_in_progress = projects.filter(
        status="in_progress", updated_at__lt=now - timedelta(days=7)
    ).count()
    inprog_this_week = projects.filter(
        status="in_progress", created_at__date__gte=week_start
    ).count()
    inprog_last_week = projects.filter(
        status="in_progress",
        created_at__date__gte=prev_week_start,
        created_at__date__lt=prev_week_end,
    ).count()
    inprog_trend_pct = _pct_change(inprog_this_week, inprog_last_week)

    completed_this_week = projects.filter(
        status="completed", updated_at__date__gte=week_start
    ).count()
    completed_last_week = projects.filter(
        status="completed",
        updated_at__date__gte=prev_week_start,
        updated_at__date__lt=prev_week_end,
    ).count()
    completed_trend_pct = _pct_change(completed_this_week, completed_last_week)

    product_counts = projects.values("product").annotate(c=Count("id")).order_by("-c")
    recent_projects = projects.select_related("technician").order_by("-created_at")[:8]

    base_num = today.year * 12 + today.month
    month_keys = []
    for i in range(11, -1, -1):
        n = base_num - i
        y = (n - 1) // 12
        m = ((n - 1) % 12) + 1
        month_keys.append(date(y, m, 1))

    created_series = (
        projects.annotate(m=TruncMonth("created_at"))
        .values("m")
        .annotate(n=Count("id"))
        .order_by("m")
    )
    completed_series = (
        projects.filter(status="completed")
        .annotate(m=TruncMonth("updated_at"))
        .values("m")
        .annotate(n=Count("id"))
        .order_by("m")
    )
    created_map = {r["m"].date(): r["n"] for r in created_series if r["m"]}
    completed_map = {r["m"].date(): r["n"] for r in completed_series if r["m"]}

    ontime_series = (
        projects.filter(status="completed")
        .annotate(m=TruncMonth("updated_at"), done_date=TruncDate("updated_at"))
        .filter(done_date__lte=F("date"))
        .values("m")
        .annotate(n=Count("id"))
        .order_by("m")
    )
    ontime_map = {r["m"].date(): r["n"] for r in ontime_series if r["m"]}

    max_count = max(
        [created_map.get(k, 0) for k in month_keys]
        + [completed_map.get(k, 0) for k in month_keys]
        + [1]
    )

    diagram_bars = []
    for k in month_keys:
        c = created_map.get(k, 0)
        d = completed_map.get(k, 0)
        ot = ontime_map.get(k, 0)
        diagram_bars.append(
            {
                "label": k.strftime("%b %y"),
                "created": c,
                "completed": d,
                "on_time": ot,
                "created_pct": int(c * 100 / max_count),
                "completed_pct": int(d * 100 / max_count),
            }
        )

    last30_created = projects.filter(created_at__gte=now - timedelta(days=30)).count()
    last30_completed_qs = projects.filter(
        status="completed", updated_at__gte=now - timedelta(days=30)
    )
    last30_completed = last30_completed_qs.count()

    last90_completed_qs = projects.filter(
        status="completed", updated_at__gte=now - timedelta(days=90)
    )
    last90_on_time = (
        last90_completed_qs.annotate(done_date=TruncDate("updated_at"))
        .filter(done_date__lte=F("date"))
        .count()
    )
    on_time_rate_90 = (
        int(last90_on_time * 100 / last90_completed_qs.count())
        if last90_completed_qs.exists()
        else 0
    )

    dur_expr = ExpressionWrapper(
        F("updated_at") - F("created_at"), output_field=DurationField()
    )
    avg_lead_td = (
        last90_completed_qs.annotate(dur=dur_expr).aggregate(avg=Avg("dur"))["avg"]
    ) or timedelta(0)
    avg_lead_days_90 = (
        round(avg_lead_td.total_seconds() / 86400, 1) if avg_lead_td else 0.0
    )

    last_12m = now - timedelta(days=365)
    wt_qs = (
        projects.filter(created_at__gte=last_12m)
        .values("work_type")
        .annotate(c=Count("id"))
        .order_by("-c")
    )
    worktype_labels = [r["work_type"] or "Non défini" for r in wt_qs]
    worktype_values = [r["c"] for r in wt_qs]

    context = {
        "technician": tech,
        "is_manager": is_manager,
        "total_projects": total_projects,
        "pending_projects": pending_projects,
        "in_progress_projects": in_progress_projects,
        "completed_projects": completed_projects,
        "new_this_week": new_this_week,
        "total_trend_pct": total_trend_pct,
        "pending_new_today": pending_new_today,
        "pending_trend_pct": pending_trend_pct,
        "overdue_in_progress": overdue_in_progress,
        "inprog_trend_pct": inprog_trend_pct,
        "completed_this_week": completed_this_week,
        "completed_trend_pct": completed_trend_pct,
        "recent_projects": recent_projects,
        "product_counts": product_counts,
        "diagram_bars": diagram_bars,
        "last30_created": last30_created,
        "last30_completed": last30_completed,
        "on_time_rate_90": on_time_rate_90,
        "avg_lead_days_90": avg_lead_days_90,
        "worktype_labels": worktype_labels,
        "worktype_values": worktype_values,
    }
    return render(request, "home.html", context)


@login_required
def analytics_view(request):
    tech = _sync_user_and_technician_from_directory(request.user)
    is_manager = getattr(tech, "is_manager", False)
    projects = (
        Project.objects.all() if is_manager else Project.objects.filter(technician=tech)
    )
    now = timezone.now()
    last_12m = now - timedelta(days=365)

    # Data for top section
    total_projects = projects.count()
    in_progress_projects_count = projects.filter(status="in_progress").count()
    completed_projects_count = projects.filter(status="completed").count()
    cancelled_projects_count = projects.filter(status="cancelled").count()

    today = now.date()
    week_start = today - timedelta(days=today.weekday())
    prev_week_start = week_start - timedelta(days=7)
    prev_week_end = week_start

    new_this_week = projects.filter(created_at__date__gte=week_start).count()
    new_prev_week = projects.filter(
        created_at__date__gte=prev_week_start, created_at__date__lt=prev_week_end
    ).count()

    def _pct_change(current: int, prev: int) -> float:
        if prev == 0:
            return 100.0 if current > 0 else 0.0
        return round((current - prev) * 100.0 / prev, 1)

    total_trend_pct = _pct_change(new_this_week, new_prev_week)

    pending_new_today = projects.filter(
        status="pending", created_at__date=today
    ).count()
    
    overdue_in_progress = projects.filter(
        status="in_progress", updated_at__lt=now - timedelta(days=7)
    ).count()
    
    completed_this_week = projects.filter(
        status="completed", updated_at__date__gte=week_start
    ).count()
    
    # Chart 1: Work Type Distribution
    wt_qs = (
        projects.filter(created_at__gte=last_12m)
        .values("work_type")
        .annotate(c=Count("id"))
        .order_by("-c")
    )
    total_worktype_projects = sum(item['c'] for item in wt_qs)
    worktype_data = []
    for r in wt_qs:
        label = r["work_type"] or "Non défini"
        value = r["c"]
        percentage = round((value / total_worktype_projects) * 100, 1) if total_worktype_projects > 0 else 0
        worktype_data.append({"label": label, "value": value, "percentage": percentage})

    # Chart 2: On-time vs. Overdue vs. Cancelled
    completed_projects_qs = projects.filter(status__in=["completed", "cancelled"], date__isnull=False)
    on_time_count = completed_projects_qs.filter(status="completed").annotate(
        done_date=TruncDate("updated_at")
    ).filter(done_date__lte=F("date")).count()
    overdue_count = completed_projects_qs.filter(status="completed").count() - on_time_count
    cancelled_count = completed_projects_qs.filter(status="cancelled").count()

    # Chart 3: Top 10 Clients
    client_qs = (
        projects.values("client_name")
        .annotate(c=Count("id"))
        .order_by("-c")[:10]
    )
    client_labels = [r["client_name"] or "N/A" for r in client_qs]
    client_values = [r["c"] for r in client_qs]

    # Chart 4: Project Status
    status_qs = projects.values("status").annotate(c=Count("id")).order_by("-c")
    status_map = {
        "pending": "En attente",
        "in_progress": "En cours",
        "completed": "Terminé",
        "on_hold": "En pause",
        "cancelled": "Annulé",
    }
    status_labels = [status_map.get(r["status"], r["status"]) for r in status_qs]
    status_values = [r["c"] for r in status_qs]

    # Chart 5: Project Specialist Workflow
    specialist_qs = (
        projects.filter(
            Q(technician__role__icontains="specialiste") | Q(technician__role__icontains="deploiement")
        )
        .values("technician__user__first_name", "technician__user__last_name")
        .annotate(c=Count("id"))
        .order_by("-c")
    )
    specialist_labels = [
        f"{r['technician__user__first_name']} {r['technician__user__last_name']}"
        for r in specialist_qs
    ]
    specialist_values = [r["c"] for r in specialist_qs]

    context = {
        "technician": tech,
        "total_projects": total_projects,
        "cancelled_projects": cancelled_projects_count,
        "in_progress_projects": in_progress_projects_count,
        "completed_projects": completed_projects_count,
        "new_this_week": new_this_week,
        "total_trend_pct": total_trend_pct,
        "pending_new_today": pending_new_today,
        "overdue_in_progress": overdue_in_progress,
        "completed_this_week": completed_this_week,
        "worktype_data": worktype_data,
        "on_time_count": on_time_count,
        "overdue_count": overdue_count,
        "cancelled_count": cancelled_count,
        "client_labels": client_labels,
        "client_values": client_values,
        "status_labels": status_labels,
        "status_values": status_values,
        "specialist_labels": specialist_labels,
        "specialist_values": specialist_values,
    }
    return render(request, "analytics.html", context)


# ------------------ Project list ------------------
@login_required
def project_list_view(request):
    tech = _sync_user_and_technician_from_directory(request.user)
    qs = (
        Project.objects.all()
        if getattr(tech, "is_manager", False)
        else Project.objects.filter(technician=tech)
    )

    status = (request.GET.get("status") or "").strip()
    environment = (request.GET.get("environment") or "").strip()
    product = (request.GET.get("product") or "").strip()
    q = (request.GET.get("q") or "").strip()
    work_type = (request.GET.get("work_type") or "").strip()

    created_by_me = request.GET.get("created_by_me") == "on"
    assigned_to_me = request.GET.get("assigned_to_me") == "on"

    date_from = (request.GET.get("date_from") or "").strip()
    date_to = (request.GET.get("date_to") or "").strip()

    sort_key = (request.GET.get("sort") or "created_desc").strip()
    per_page = int(request.GET.get("per_page") or 10)
    per_page_choices = [10, 20, 50, 100]

    if status:
        qs = qs.filter(status=status)
    if environment:
        qs = qs.filter(environment=environment)
    if product:
        qs = qs.filter(product=product)
    if work_type:
        qs = qs.filter(work_type=work_type)

    if q:
        qs = qs.filter(
            Q(project_number__icontains=q)
            | Q(title__icontains=q)
            | Q(client_name__icontains=q)
            | Q(product__icontains=q)
            | Q(technician__user__first_name__icontains=q)
            | Q(technician__user__last_name__icontains=q)
            | Q(ruleset__name__icontains=q)
        )

    if created_by_me:
        qs = qs.filter(created_by=request.user)
    if assigned_to_me:
        qs = qs.filter(Q(technician=tech) | Q(assigned_to=request.user))

    def _parse_date(s):
        try:
            return datetime.strptime(s, "%Y-%m-%d").date()
        except Exception:
            return None

    d_from = _parse_date(date_from)
    d_to = _parse_date(date_to)
    if d_from:
        qs = qs.filter(date__gte=d_from)
    if d_to:
        qs = qs.filter(date__lt=(d_to + timedelta(days=1)))

    sort_map = {
        "created_desc": "-created_at",
        "created_asc": "created_at",
        "date_desc": "-date",
        "date_asc": "date",
        "client_az": "client_name",
        "client_za": "-client_name",
        "product_az": "product",
        "product_za": "-product",
        "status": "status",
    }
    qs = qs.order_by(sort_map.get(sort_key, "-created_at"))

    if request.GET.get("export") == "1":
        resp = HttpResponse(content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = 'attachment; filename="projects.csv"'
        resp.write(
            "Numéro,Titre,Client,Produit,Environnement,Statut,Date,Créé le,Modifié le\n"
        )
        for p in qs.select_related("technician", "created_by"):
            row = [
                p.project_number,
                (p.title or "").replace(",", " "),
                (p.client_name or "").replace(",", " "),
                p.product,
                p.get_environment_display(),
                p.get_status_display(),
                p.date.isoformat(),
                p.created_at.isoformat(timespec="seconds"),
                p.updated_at.isoformat(timespec="seconds"),
            ]
            resp.write(",".join(row) + "\n")
        return resp

    paginator = Paginator(
        qs.select_related("technician").only(
            "id",
            "project_number",
            "title",
            "client_name",
            "product",
            "environment",
            "status",
            "created_at",
            "date",
            "technician__user__first_name",
            "technician__user__last_name",
        ),
        per_page,
    )
    page_obj = paginator.get_page(request.GET.get("page") or 1)

    status_counts = Project.objects.values("status").annotate(c=Count("id"))
    status_map = {s["status"]: s["c"] for s in status_counts}

    products = list(
        Project.objects.order_by().values_list("product", flat=True).distinct()
    )

    context = {
        "technician": tech,
        "projects": page_obj,
        "page_obj": page_obj,
        "paginator": paginator,
        "status": status,
        "environment": environment,
        "product": product,
        "work_type": work_type,
        "q": q,
        "created_by_me": created_by_me,
        "assigned_to_me": assigned_to_me,
        "date_from": date_from,
        "date_to": date_to,
        "sort": sort_key,
        "per_page": per_page,
        "per_page_choices": per_page_choices,
        "status_map": status_map,
        "products": products,
    }
    return render(request, "project_list.html", context)


# ------------------ Global search ------------------
@login_required
def search_view(request):
    q = (request.GET.get("q") or "").strip()
    tech = _sync_user_and_technician_from_directory(request.user)
    base = (
        Project.objects.all()
        if getattr(tech, "is_manager", False)
        else Project.objects.filter(technician=tech)
    )

    projects = base.none()
    matched_techs = Technician.objects.none()

    if q:
        parts = [p for p in q.split() if p]
        cond = Q()
        for p in parts:
            cond |= (
                Q(title__icontains=p)
                | Q(project_number__icontains=p)
                | Q(client_name__icontains=p)
                | Q(product__icontains=p)
                | Q(ruleset__name__icontains=p)
                | Q(technician__user__first_name__icontains=p)
                | Q(technician__user__last_name__icontains=p)
                | Q(technician__user__username__icontains=p)
                | Q(created_by__first_name__icontains=p)
                | Q(created_by__last_name__icontains=p)
                | Q(created_by__username__icontains=p)
            )

        projects = (
            base.select_related(
                "technician", "technician__user", "created_by", "ruleset"
            )
            .filter(cond)
            .order_by("-created_at")
        )

        matched_techs = (
            Technician.objects.filter(
                Q(user__first_name__icontains=q)
                | Q(user__last_name__icontains=q)
                | Q(user__username__icontains=q)
            )
            .annotate(total=Count("projects"))
            .order_by("-total")[:10]
        )

    paginator = Paginator(projects, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    ctx = {
        "q": q,
        "projects": page_obj.object_list,
        "page_obj": page_obj,
        "matched_techs": matched_techs,
        "technician": tech,
        "total_found": projects.count() if q else 0,
    }
    return render(request, "search_results.html", ctx)


# ------------------ Edit existing project ------------------
@login_required
def project_update_view(request, pk):
    project = get_object_or_404(Project, pk=pk)
    # The new form handles everything client-side, so we just render the page.
    # We can pass project data to the template if the wizard needs to be pre-filled.
    return render(request, "project_form.html", {"project": project})


# ------------------ Create (role-based flow) ------------------


def _is_planner_or_manager(user) -> bool:
    tech = _sync_user_and_technician_from_directory(user)
    role = (getattr(tech, "role", "") or "").lower()
    return bool(getattr(tech, "is_manager", False) or "planification" in role)


@login_required
def project_create_view(request, pk=None):
    """
    This view now simply renders the wizard form.
    The form is self-contained and will post data to the new save view.
    """
    tech = _sync_user_and_technician_from_directory(request.user)

    if pk:
        project = get_object_or_404(Project, pk=pk)
    else:
        project = None

    # Role-based redirection
    if _is_planner_or_manager_from_tech(tech) and not project:
        return redirect("coordination_form")

    if request.method == "POST":
        form = ProjectForm(request.POST, request.FILES, instance=project)
        if form.is_valid():
            project = form.save(commit=False)
            if not project.pk:
                project.created_by = request.user
                project.technician = tech
            project.save()
            messages.success(
                request, f"Projet {'mis à jour' if project.pk else 'créé'} avec succès."
            )
            return redirect("project_detail", pk=project.pk)
    else:
        form = ProjectForm(instance=project)

    return render(request, "project_form.html", {"form": form, "technician": tech})


# ------------------ Detail ------------------
@login_required
def project_detail_view(request, pk):
    tech = _sync_user_and_technician_from_directory(request.user)
    p = (
        get_object_or_404(Project, pk=pk)
        if getattr(tech, "is_manager", False)
        else get_object_or_404(
            Project, Q(pk=pk) & (Q(technician=tech) | Q(created_by=request.user))
        )
    )
    is_creator = p.created_by_id == request.user.id

    # progress bar value for phases
    total_phases = 3
    phases_completed = p.phases_completed
    phase_progress_pct = int(phases_completed * 100 / total_phases)

    items = (
        ChecklistItem.objects.filter(project=p)
        .prefetch_related("notes", "images")
        .order_by("order", "id")
    )

    context = {
        "project": p,
        "technician": tech,
        "is_creator": is_creator,
        "phase_progress_pct": phase_progress_pct,
        "items": items,
        "total_phases": total_phases,
        "phases_completed": phases_completed,
    }
    return render(request, "project_detail.html", context)


# ------------------ Team dashboard ------------------
@login_required
def team_dashboard_view(request):
    tech = _sync_user_and_technician_from_directory(request.user)
    if not getattr(tech, "is_manager", False):
        messages.error(request, "Accès réservé aux managers.")
        return redirect("home")

    techs = (
        Technician.objects.select_related("user")
        .annotate(
            total=Count("projects", distinct=True),
            done=Count(
                "projects", filter=Q(projects__status="completed"), distinct=True
            ),
            doing=Count(
                "projects", filter=Q(projects__status="in_progress"), distinct=True
            ),
            pending=Count(
                "projects", filter=Q(projects__status="pending"), distinct=True
            ),
        )
        .order_by("user__first_name", "user__last_name")
    )

    team = []
    for t in techs:
        total = t.total or 0
        pct = int((t.done / total) * 100) if total else 0
        recent = Project.objects.filter(technician=t).order_by("-created_at")[:3]
        team.append({"tech": t, "pct": pct, "recent": recent})

    return render(request, "team_dashboard.html", {"team": team, "technician": tech})


# ------------------ Phase updates ------------------
@require_POST
@login_required
def project_phase_update_view(request, pk):
    tech = _sync_user_and_technician_from_directory(request.user)
    if getattr(tech, "is_manager", False):
        p = get_object_or_404(Project, pk=pk)
    else:
        p = get_object_or_404(Project, pk=pk, technician=tech)

    phase = request.POST.get("phase")
    new_state = request.POST.get("set")  # 'not_started' | 'in_progress' | 'completed'
    valid_phases = {"preparation", "execution", "validation"}
    valid_states = {"not_started", "in_progress", "completed"}

    if phase not in valid_phases or new_state not in valid_states:
        messages.error(request, "Action invalide.")
        return redirect("project_detail", pk=p.pk)

    if (
        phase == "execution"
        and new_state in ("in_progress", "completed")
        and p.preparation_phase != "completed"
    ):
        messages.error(
            request, "Terminez la préparation avant de démarrer l'exécution."
        )
        return redirect("project_detail", pk=p.pk)
    if (
        phase == "validation"
        and new_state in ("in_progress", "completed")
        and p.execution_phase != "completed"
    ):
        messages.error(request, "Terminez l'exécution avant de démarrer la validation.")
        return redirect("project_detail", pk=p.pk)

    if phase == "preparation":
        p.preparation_phase = new_state
        label = "Préparation"
        display = p.get_preparation_phase_display()
    elif phase == "execution":
        p.execution_phase = new_state
        label = "Exécution"
        display = p.get_execution_phase_display()
    else:
        p.validation_phase = new_state
        label = "Validation"
        display = p.get_validation_phase_display()

    try:
        p.save()
        TimelineEntry.objects.create(
            project=p,
            environment=p.environment,
            event_label=f"{label} → {display}",
            event_time=timezone.now(),
        )
        messages.success(request, f"{label} mise à jour.")
    except Exception as e:
        messages.error(request, f"Impossible de modifier la phase: {e}")

    return redirect("project_detail", pk=p.pk)


# =====================================================================
# ===============  CHECKLIST: JSON import / notes / images  ===========
# =====================================================================
@login_required
@require_POST
def checklist_import_view(request, pk):
    tech = _sync_user_and_technician_from_directory(request.user)
    project = (
        get_object_or_404(Project, pk=pk)
        if getattr(tech, "is_manager", False)
        else get_object_or_404(
            Project, Q(pk=pk) & (Q(technician=tech) | Q(created_by=request.user))
        )
    )

    form = ChecklistJSONUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "Fichier invalide.")
        return redirect("project_detail", pk=project.pk)

    payload_bytes = form.cleaned_data["json_file"].read()
    try:
        data = json.loads(payload_bytes.decode("utf-8"))
    except Exception:
        messages.error(request, "Impossible de parser le JSON.")
        return redirect("project_detail", pk=project.pk)

    items = (data or {}).get("items") or []
    if not isinstance(items, list) or not items:
        messages.error(request, "JSON invalide: aucun item.")
        return redirect("project_detail", pk=project.pk)

    ChecklistItem.objects.filter(project=project).delete()
    for i, item in enumerate(items):
        label = (
            (item.get("label") or "").strip()
            if isinstance(item, dict)
            else str(item).strip()
        )
        if not label:
            label = f"Étape {i+1}"
        ChecklistItem.objects.create(project=project, label=label, order=i)

    project.checklist_data = {
        "items": [
            {"label": (x.get("label") if isinstance(x, dict) else str(x)) or ""}
            for x in items
        ]
    }
    project.save(update_fields=["checklist_data", "updated_at"])

    messages.success(request, f"Checklist importée: {len(items)} étapes.")
    return redirect("project_detail", pk=project.pk)


@login_required
@require_POST
def checklist_item_add_note_view(request, item_id):
    tech = _sync_user_and_technician_from_directory(request.user)
    item = get_object_or_404(ChecklistItem, pk=item_id)

    if (
        not getattr(tech, "is_manager", False)
        and item.project.technician_id != tech.id
        and item.project.created_by_id != request.user.id
    ):
        return HttpResponseBadRequest("Non autorisé")

    form = ChecklistItemUpdateForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "Formulaire invalide.")
        return redirect("project_detail", pk=item.project_id)

    text = form.cleaned_data.get("text", "").strip()
    if text:
        ChecklistItemNote.objects.create(item=item, author=request.user, text=text)

    for f in request.FILES.getlist("images"):
        if f:
            ChecklistItemImage.objects.create(item=item, image=f)

    messages.success(request, "Note/Images ajoutées.")
    return redirect("project_detail", pk=item.project_id)


@login_required
@require_POST
def checklist_item_toggle_view(request, item_id):
    tech = _sync_user_and_technician_from_directory(request.user)
    item = get_object_or_404(ChecklistItem, pk=item_id)

    if (
        not getattr(tech, "is_manager", False)
        and item.project.technician_id != tech.id
        and item.project.created_by_id != request.user.id
    ):
        return HttpResponseBadRequest("Non autorisé")

    new_state = request.POST.get("completed") == "1"
    item.completed = new_state
    update_fields = ["completed"]
    if hasattr(item, "completed_at"):
        item.completed_at = timezone.now() if new_state else None
        update_fields.append("completed_at")
    item.save(update_fields=update_fields)

    messages.success(request, "Étape mise à jour.")
    return redirect("project_detail", pk=item.project_id)


@login_required
def project_checklist_pdf_view(request, pk):
    tech = _sync_user_and_technician_from_directory(request.user)
    project = (
        get_object_or_404(Project, pk=pk)
        if getattr(tech, "is_manager", False)
        else get_object_or_404(
            Project, Q(pk=pk) & (Q(technician=tech) | Q(created_by=request.user))
        )
    )

    items = (
        ChecklistItem.objects.filter(project=project)
        .prefetch_related("notes", "images")
        .order_by("order", "id")
    )

    render_to_string(
        "checklist_pdf.html",
        {
            "project": project,
            "items": items,
            "generated_at": timezone.now(),
            "user": request.user,
        },
    )

    pdf_io = io.BytesIO()
    # pisa_status = pisa.CreatePDF(io.BytesIO(html.encode("utf-8")), dest=pdf_io)
    # if pisa_status.err:
    #     return HttpResponseBadRequest("Échec de génération du PDF")

    pdf_io.seek(0)
    filename = (
        f"Checklist_{project.project_number}.pdf"
        if project.project_number
        else "Checklist.pdf"
    )
    return FileResponse(pdf_io, filename=filename, content_type="application/pdf")


# --- Profile (kept for URL import) ---
@login_required
def profile_view(request):
    tech, _ = Technician.objects.get_or_create(
        user=request.user, defaults={"role": "Technicien"}
    )

    assigned_qs = Project.objects.filter(technician=tech)
    created_qs = Project.objects.filter(created_by=request.user)

    total = assigned_qs.count()
    pending = assigned_qs.filter(status="pending").count()
    doing = assigned_qs.filter(status="in_progress").count()
    done = assigned_qs.filter(status="completed").count()

    on_time = (
        assigned_qs.filter(status="completed")
        .annotate(_done_date=TruncDate("updated_at"))
        .filter(_done_date__lte=F("date"))
        .count()
    )
    on_time_rate = int((on_time / done) * 100) if done else 0

    assigned_list = list(assigned_qs[:500])
    completion_avg = (
        int(sum(p.completion_percentage for p in assigned_list) / total) if total else 0
    )

    recent_assigned = assigned_qs.select_related("technician").order_by("-created_at")[
        :10
    ]
    recent_created = created_qs.select_related("technician").order_by("-created_at")[
        :10
    ]

    product_counts = (
        assigned_qs.values("product").annotate(c=Count("id")).order_by("-c")
    )

    context = {
        "technician": tech,
        "total": total,
        "pending": pending,
        "doing": doing,
        "done": done,
        "on_time_rate": on_time_rate,
        "completion_avg": completion_avg,
        "recent_assigned": recent_assigned,
        "recent_created": recent_created,
        "product_counts": product_counts,
    }
    return render(request, "profile.html", context)
