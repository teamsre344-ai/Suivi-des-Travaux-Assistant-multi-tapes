from datetime import date, datetime, timedelta
import io
import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q, F, Count, Avg, DurationField, ExpressionWrapper
from django.db.models.functions import TruncMonth, TruncDate
from django.http import HttpResponse, FileResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.http import require_POST
from xhtml2pdf import pisa

from .forms import (
    PasswordlessLoginForm,
    ProjectForm,
    ChecklistJSONUploadForm,
    ChecklistItemUpdateForm,
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
# Helpers for team directory/roles
# --------------------------------
def _directory_entry_for(email: str) -> dict | None:
    if not email:
        return None
    directory = getattr(settings, "TEAM_DIRECTORY", {}) or {}
    return directory.get(email.lower())

def _sync_user_and_technician_from_directory(user: User) -> Technician:
    """
    Ensure the User (names) and Technician (role/is_manager) reflect TEAM_DIRECTORY.
    If no directory entry, keep existing values (role defaults to 'Technicien').
    """
    entry = _directory_entry_for(user.email)
    defaults_role = (entry or {}).get("role") or "Technicien"
    tech, _ = Technician.objects.get_or_create(user=user, defaults={'role': defaults_role})

    if entry:
        changed = False
        if entry.get("first_name") and user.first_name != entry["first_name"]:
            user.first_name = entry["first_name"]; changed = True
        if entry.get("last_name") and user.last_name != entry["last_name"]:
            user.last_name = entry["last_name"]; changed = True
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
            out.append(c2); seen.add(c2)
    return out

# ------------------ Auth ------------------
def login_view(request):
    """
    Passwordless login:
    - asks for email only
    - if a matching User.email exists (case-insensitive), log them in
    """
    if request.user.is_authenticated:
        return redirect('home')

    form = PasswordlessLoginForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        raw = form.cleaned_data['email'].strip()
        # Support both lgisolutions.com and logibec.com + bare local part
        for candidate in _normalize_email_for_lookup(raw):
            user = User.objects.filter(email__iexact=candidate).first()
            if user:
                login(request, user, backend='django.contrib.auth.backends.ModelBackend')
                messages.success(request, "Connexion réussie.")
                return redirect('home')

        messages.error(request, "Aucun utilisateur trouvé avec cet e-mail.")
        # fall through to re-render form

    return render(request, 'login.html', {'form': form})

@login_required
def logout_view(request):
    logout(request)
    return redirect('login')

# ------------------ Dashboard ------------------
@login_required
def home_view(request):
    tech = _sync_user_and_technician_from_directory(request.user)
    is_manager = getattr(tech, 'is_manager', False)
    projects = Project.objects.all() if is_manager else Project.objects.filter(technician=tech)

    total_projects = projects.count()
    pending_projects = projects.filter(status='pending').count()
    in_progress_projects = projects.filter(status='in_progress').count()
    completed_projects = projects.filter(status='completed').count()

    now = timezone.now()
    today = now.date()
    week_start = today - timedelta(days=today.weekday())
    prev_week_start = week_start - timedelta(days=7)
    prev_week_end = week_start

    new_this_week = projects.filter(created_at__date__gte=week_start).count()
    new_prev_week = projects.filter(
        created_at__date__gte=prev_week_start,
        created_at__date__lt=prev_week_end
    ).count()

    def _pct_change(current: int, prev: int) -> float:
        if prev == 0:
            return 100.0 if current > 0 else 0.0
        return round((current - prev) * 100.0 / prev, 1)

    total_trend_pct = _pct_change(new_this_week, new_prev_week)

    pending_new_today = projects.filter(status='pending', created_at__date=today).count()
    pending_this_week = projects.filter(status='pending', created_at__date__gte=week_start).count()
    pending_last_week = projects.filter(
        status='pending',
        created_at__date__gte=prev_week_start,
        created_at__date__lt=prev_week_end
    ).count()
    pending_trend_pct = _pct_change(pending_this_week, pending_last_week)

    overdue_in_progress = projects.filter(
        status='in_progress',
        updated_at__lt=now - timedelta(days=7)
    ).count()
    inprog_this_week = projects.filter(status='in_progress', created_at__date__gte=week_start).count()
    inprog_last_week = projects.filter(
        status='in_progress',
        created_at__date__gte=prev_week_start,
        created_at__date__lt=prev_week_end
    ).count()
    inprog_trend_pct = _pct_change(inprog_this_week, inprog_last_week)

    completed_this_week = projects.filter(status='completed', updated_at__date__gte=week_start).count()
    completed_last_week = projects.filter(
        status='completed',
        updated_at__date__gte=prev_week_start,
        updated_at__date__lt=prev_week_end
    ).count()
    completed_trend_pct = _pct_change(completed_this_week, completed_last_week)

    product_counts = projects.values('product').annotate(c=Count('id')).order_by('-c')
    recent_projects = projects.select_related('technician').order_by('-created_at')[:8]

    base_num = today.year * 12 + today.month
    month_keys = []
    for i in range(11, -1, -1):
        n = base_num - i
        y = (n - 1) // 12
        m = ((n - 1) % 12) + 1
        month_keys.append(date(y, m, 1))

    created_series = (projects
                      .annotate(m=TruncMonth('created_at'))
                      .values('m')
                      .annotate(n=Count('id'))
                      .order_by('m'))
    completed_series = (projects.filter(status='completed')
                        .annotate(m=TruncMonth('updated_at'))
                        .values('m')
                        .annotate(n=Count('id'))
                        .order_by('m'))
    created_map = {r['m'].date(): r['n'] for r in created_series if r['m']}
    completed_map = {r['m'].date(): r['n'] for r in completed_series if r['m']}

    ontime_series = (projects.filter(status='completed')
                     .annotate(m=TruncMonth('updated_at'), done_date=TruncDate('updated_at'))
                     .filter(done_date__lte=F('date'))
                     .values('m')
                     .annotate(n=Count('id'))
                     .order_by('m'))
    ontime_map = {r['m'].date(): r['n'] for r in ontime_series if r['m']}

    max_count = max([created_map.get(k, 0) for k in month_keys] +
                    [completed_map.get(k, 0) for k in month_keys] + [1])

    diagram_bars = []
    for k in month_keys:
        c = created_map.get(k, 0)
        d = completed_map.get(k, 0)
        ot = ontime_map.get(k, 0)
        diagram_bars.append({
            'label': k.strftime('%b %y'),
            'created': c,
            'completed': d,
            'on_time': ot,
            'created_pct': int(c * 100 / max_count),
            'completed_pct': int(d * 100 / max_count),
        })

    last30_created = projects.filter(created_at__gte=now - timedelta(days=30)).count()
    last30_completed_qs = projects.filter(status='completed', updated_at__gte=now - timedelta(days=30))
    last30_completed = last30_completed_qs.count()

    last90_completed_qs = projects.filter(status='completed', updated_at__gte=now - timedelta(days=90))
    last90_on_time = (last90_completed_qs
                      .annotate(done_date=TruncDate('updated_at'))
                      .filter(done_date__lte=F('date'))
                      .count())
    on_time_rate_90 = int(last90_on_time * 100 / last90_completed_qs.count()) if last90_completed_qs.exists() else 0

    dur_expr = ExpressionWrapper(F('updated_at') - F('created_at'), output_field=DurationField())
    avg_lead_td = (last90_completed_qs.annotate(dur=dur_expr).aggregate(avg=Avg('dur'))['avg']) or timedelta(0)
    avg_lead_days_90 = round(avg_lead_td.total_seconds() / 86400, 1) if avg_lead_td else 0.0

    last_12m = now - timedelta(days=365)
    wt_qs = (projects.filter(created_at__gte=last_12m)
             .values('work_type')
             .annotate(c=Count('id'))
             .order_by('-c'))
    worktype_labels = [r['work_type'] or 'Non défini' for r in wt_qs]
    worktype_values = [r['c'] for r in wt_qs]

    context = {
        'technician': tech,
        'is_manager': is_manager,

        'total_projects': total_projects,
        'pending_projects': pending_projects,
        'in_progress_projects': in_progress_projects,
        'completed_projects': completed_projects,

        'new_this_week': new_this_week,
        'total_trend_pct': total_trend_pct,
        'pending_new_today': pending_new_today,
        'pending_trend_pct': pending_trend_pct,
        'overdue_in_progress': overdue_in_progress,
        'inprog_trend_pct': inprog_trend_pct,
        'completed_this_week': completed_this_week,
        'completed_trend_pct': completed_trend_pct,

        'recent_projects': recent_projects,
        'product_counts': product_counts,

        'diagram_bars': diagram_bars,
        'last30_created': last30_created,
        'last30_completed': last30_completed,
        'on_time_rate_90': on_time_rate_90,
        'avg_lead_days_90': avg_lead_days_90,

        'worktype_labels': worktype_labels,
        'worktype_values': worktype_values,
    }
    return render(request, 'home.html', context)

@login_required
def analytics_view(request):
    tech = _sync_user_and_technician_from_directory(request.user)
    is_manager = getattr(tech, 'is_manager', False)
    projects = Project.objects.all() if is_manager else Project.objects.filter(technician=tech)
    return render(request, "analytics.html", {"technician": tech, "total": projects.count()})

# ------------------ Project list ------------------
@login_required
def project_list_view(request):
    tech = _sync_user_and_technician_from_directory(request.user)
    qs = Project.objects.all() if getattr(tech, 'is_manager', False) else Project.objects.filter(technician=tech)

    status = (request.GET.get('status') or '').strip()
    environment = (request.GET.get('environment') or '').strip()
    product = (request.GET.get('product') or '').strip()
    q = (request.GET.get('q') or '').strip()
    work_type = (request.GET.get('work_type') or '').strip()

    created_by_me = request.GET.get('created_by_me') == 'on'
    assigned_to_me = request.GET.get('assigned_to_me') == 'on'

    date_from = (request.GET.get('date_from') or '').strip()
    date_to = (request.GET.get('date_to') or '').strip()

    sort_key = (request.GET.get('sort') or 'created_desc').strip()
    per_page = int(request.GET.get('per_page') or 10)
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
            Q(project_number__icontains=q) |
            Q(title__icontains=q) |
            Q(client_name__icontains=q) |
            Q(product__icontains=q) |
            Q(technician__user__first_name__icontains=q) |
            Q(technician__user__last_name__icontains=q) |
            Q(ruleset__name__icontains=q)
        )

    if created_by_me:
        qs = qs.filter(created_by=request.user)
    if assigned_to_me:
        qs = qs.filter(technician=tech)

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
        'created_desc': '-created_at',
        'created_asc': 'created_at',
        'date_desc': '-date',
        'date_asc': 'date',
        'client_az': 'client_name',
        'client_za': '-client_name',
        'product_az': 'product',
        'product_za': '-product',
        'status': 'status',
    }
    qs = qs.order_by(sort_map.get(sort_key, '-created_at'))

    if request.GET.get('export') == '1':
        resp = HttpResponse(content_type='text/csv; charset=utf-8')
        resp['Content-Disposition'] = 'attachment; filename="projects.csv"'
        resp.write("Numéro,Titre,Client,Produit,Environnement,Statut,Date,Créé le,Modifié le\n")
        for p in qs.select_related('technician', 'created_by'):
            row = [
                p.project_number,
                (p.title or '').replace(',', ' '),
                (p.client_name or '').replace(',', ' '),
                p.product,
                p.get_environment_display(),
                p.get_status_display(),
                p.date.isoformat(),
                p.created_at.isoformat(timespec='seconds'),
                p.updated_at.isoformat(timespec='seconds'),
            ]
            resp.write(",".join(row) + "\n")
        return resp

    paginator = Paginator(qs.select_related('technician').only(
        'id', 'project_number', 'title', 'client_name', 'product', 'environment',
        'status', 'created_at', 'date', 'technician__user__first_name', 'technician__user__last_name'
    ), per_page)
    page_obj = paginator.get_page(request.GET.get('page') or 1)

    status_counts = Project.objects.values('status').annotate(c=Count('id'))
    status_map = {s['status']: s['c'] for s in status_counts}

    products = list(Project.objects.order_by().values_list('product', flat=True).distinct())

    context = {
        'technician': tech,
        'projects': page_obj,
        'page_obj': page_obj,
        'paginator': paginator,

        'status': status,
        'environment': environment,
        'product': product,
        'work_type': work_type,
        'q': q,
        'created_by_me': created_by_me,
        'assigned_to_me': assigned_to_me,
        'date_from': date_from,
        'date_to': date_to,
        'sort': sort_key,
        'per_page': per_page,
        'per_page_choices': per_page_choices,

        'status_map': status_map,
        'products': products,
    }
    return render(request, 'project_list.html', context)

# ------------------ Global search ------------------
@login_required
def search_view(request):
    q = (request.GET.get('q') or '').strip()
    tech = _sync_user_and_technician_from_directory(request.user)
    base = Project.objects.all() if getattr(tech, 'is_manager', False) else Project.objects.filter(technician=tech)

    projects = base.none()
    matched_techs = Technician.objects.none()

    if q:
        parts = [p for p in q.split() if p]
        cond = Q()
        for p in parts:
            cond |= (
                Q(title__icontains=p) |
                Q(project_number__icontains=p) |
                Q(client_name__icontains=p) |
                Q(product__icontains=p) |
                Q(ruleset__name__icontains=p) |
                Q(technician__user__first_name__icontains=p) |
                Q(technician__user__last_name__icontains=p) |
                Q(technician__user__username__icontains=p) |
                Q(created_by__first_name__icontains=p) |
                Q(created_by__last_name__icontains=p) |
                Q(created_by__username__icontains=p)
            )

        projects = (base
                    .select_related('technician', 'technician__user', 'created_by', 'ruleset')
                    .filter(cond)
                    .order_by('-created_at'))

        matched_techs = (Technician.objects
                         .filter(
                             Q(user__first_name__icontains=q) |
                             Q(user__last_name__icontains=q) |
                             Q(user__username__icontains=q)
                         )
                         .annotate(total=Count('projects'))
                         .order_by('-total')[:10])

    paginator = Paginator(projects, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    ctx = {
        'q': q,
        'projects': page_obj.object_list,
        'page_obj': page_obj,
        'matched_techs': matched_techs,
        'technician': tech,
        'total_found': projects.count() if q else 0,
    }
    return render(request, 'search_results.html', ctx)

# ------------------ Create / Detail ------------------
@login_required
def project_create_view(request):
    tech = _sync_user_and_technician_from_directory(request.user)

    ruleset_name = (request.GET.get('ruleset') or '').strip()
    ruleset = None
    if ruleset_name:
        from .models import ProjectRuleSet
        ruleset = ProjectRuleSet.objects.filter(name=ruleset_name).first()

    if request.method == 'POST':
        form = ProjectForm(request.POST)
        if form.is_valid():
            p = form.save(commit=False)
            p.created_by = request.user
            p.technician = tech
            env_label = 'Test' if p.environment == 'test' else 'Production'
            p.title = f"{env_label} — {p.client_name} — {p.product} — {p.project_number}"

            if ruleset:
                p.ruleset = ruleset
                if ruleset.default_checklist:
                    p.checklist_data = ruleset.default_checklist

            if not p.checklist_data:
                checklist_items = [
                    "Demander les accès pour tous les serveurs",
                    "Tester l'application (fonctionnement)",
                    "Valider la version applicative, nom BD, établissement",
                    "Valider l'heure début/fin du backup",
                    "Valider les prérequis selon le type de travaux",
                    "Suivre la procédure selon le produit et le type de travaux",
                    "Valider FUSE",
                    "Valider certificats",
                    "Accord ROLLBACK — DBA + Responsable",
                    "Validation du bon fonctionnement avec le client",
                ]
                p.checklist_data = {'items': [{'label': x, 'completed': False} for x in checklist_items]}

            p.save()

            for idx, item in enumerate((p.checklist_data or {}).get('items', [])):
                ChecklistItem.objects.create(
                    project=p,
                    label=item.get('label', f'Item {idx+1}'),
                    order=idx,
                    completed=bool(item.get('completed'))
                )

            messages.success(request, 'Projet créé avec succès.')
            return redirect('project_detail', pk=p.pk)
    else:
        initial = {}
        if ruleset:
            if ruleset.default_environment:
                initial['environment'] = ruleset.default_environment
            if ruleset.default_product:
                initial['product'] = ruleset.default_product
            if ruleset.default_work_type:
                initial['work_type'] = ruleset.default_work_type
        form = ProjectForm(initial=initial)

    return render(request, 'project_form.html', {'form': form, 'technician': tech})

@login_required
def project_detail_view(request, pk):
    tech = _sync_user_and_technician_from_directory(request.user)
    p = get_object_or_404(Project, pk=pk) if getattr(tech, 'is_manager', False) else get_object_or_404(
        Project, Q(pk=pk) & (Q(technician=tech) | Q(created_by=request.user))
    )
    is_creator = (p.created_by_id == request.user.id)
    return render(request, 'project_detail.html', {'project': p, 'technician': tech, 'is_creator': is_creator})

# ------------------ Team dashboard ------------------
@login_required
def team_dashboard_view(request):
    tech = _sync_user_and_technician_from_directory(request.user)
    if not getattr(tech, 'is_manager', False):
        messages.error(request, 'Accès réservé aux managers.')
        return redirect('home')

    techs = (
        Technician.objects
        .select_related('user')
        .annotate(
            total=Count('projects', distinct=True),
            done=Count('projects', filter=Q(projects__status='completed'), distinct=True),
            doing=Count('projects', filter=Q(projects__status='in_progress'), distinct=True),
            pending=Count('projects', filter=Q(projects__status='pending'), distinct=True),
        )
        .order_by('user__first_name', 'user__last_name')
    )

    team = []
    for t in techs:
        total = t.total or 0
        pct = int((t.done / total) * 100) if total else 0
        recent = Project.objects.filter(technician=t).order_by('-created_at')[:3]
        team.append({'tech': t, 'pct': pct, 'recent': recent})

    return render(request, 'team_dashboard.html', {'team': team, 'technician': tech})

# ------------------ Phase updates ------------------
@require_POST
@login_required
def project_phase_update_view(request, pk):
    tech = _sync_user_and_technician_from_directory(request.user)
    if getattr(tech, 'is_manager', False):
        p = get_object_or_404(Project, pk=pk)
    else:
        p = get_object_or_404(Project, pk=pk, technician=tech)

    phase = request.POST.get('phase')
    new_state = request.POST.get('set')  # 'not_started' | 'in_progress' | 'completed'
    valid_phases = {'preparation', 'execution', 'validation'}
    valid_states = {'not_started', 'in_progress', 'completed'}

    if phase not in valid_phases or new_state not in valid_states:
        messages.error(request, "Action invalide.")
        return redirect('project_detail', pk=p.pk)

    if phase == 'execution' and new_state in ('in_progress', 'completed') and p.preparation_phase != 'completed':
        messages.error(request, "Terminez la préparation avant de démarrer l'exécution.")
        return redirect('project_detail', pk=p.pk)
    if phase == 'validation' and new_state in ('in_progress', 'completed') and p.execution_phase != 'completed':
        messages.error(request, "Terminez l'exécution avant de démarrer la validation.")
        return redirect('project_detail', pk=p.pk)

    if phase == 'preparation':
        p.preparation_phase = new_state
        label = "Préparation"
        display = p.get_preparation_phase_display()
    elif phase == 'execution':
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

    return redirect('project_detail', pk=p.pk)

# =====================================================================
# ===============  CHECKLIST: JSON import / notes / images  ===========
# =====================================================================
@login_required
@require_POST
def checklist_import_view(request, pk):
    tech = _sync_user_and_technician_from_directory(request.user)
    project = get_object_or_404(Project, pk=pk) if getattr(tech, 'is_manager', False) else get_object_or_404(
        Project, Q(pk=pk) & (Q(technician=tech) | Q(created_by=request.user))
    )

    form = ChecklistJSONUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "Fichier invalide.")
        return redirect('project_detail', pk=project.pk)

    payload_bytes = form.cleaned_data['json_file'].read()
    try:
        data = json.loads(payload_bytes.decode('utf-8'))
    except Exception:
        messages.error(request, "Impossible de parser le JSON.")
        return redirect('project_detail', pk=project.pk)

    items = (data or {}).get('items') or []
    if not isinstance(items, list) or not items:
        messages.error(request, "JSON invalide: aucun item.")
        return redirect('project_detail', pk=project.pk)

    ChecklistItem.objects.filter(project=project).delete()
    for i, item in enumerate(items):
        label = (item.get('label') or '').strip() if isinstance(item, dict) else str(item).strip()
        if not label:
            label = f"Étape {i+1}"
        ChecklistItem.objects.create(project=project, label=label, order=i)

    project.checklist_data = {'items': [{'label': (x.get('label') if isinstance(x, dict) else str(x)) or ''} for x in items]}
    project.save(update_fields=['checklist_data', 'updated_at'])

    messages.success(request, f"Checklist importée: {len(items)} étapes.")
    return redirect('project_detail', pk=project.pk)

@login_required
@require_POST
def checklist_item_add_note_view(request, item_id):
    tech = _sync_user_and_technician_from_directory(request.user)
    item = get_object_or_404(ChecklistItem, pk=item_id)

    if not getattr(tech, 'is_manager', False) and item.project.technician_id != tech.id and item.project.created_by_id != request.user.id:
        return HttpResponseBadRequest("Non autorisé")

    form = ChecklistItemUpdateForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "Formulaire invalide.")
        return redirect('project_detail', pk=item.project_id)

    text = form.cleaned_data.get('text', '').strip()
    if text:
        ChecklistItemNote.objects.create(item=item, author=request.user, text=text)

    for f in request.FILES.getlist('images'):
        if f:
            ChecklistItemImage.objects.create(item=item, image=f)

    messages.success(request, "Note/Images ajoutées.")
    return redirect('project_detail', pk=item.project_id)

@login_required
@require_POST
def checklist_item_toggle_view(request, item_id):
    tech = _sync_user_and_technician_from_directory(request.user)
    item = get_object_or_404(ChecklistItem, pk=item_id)

    if not getattr(tech, 'is_manager', False) and item.project.technician_id != tech.id and item.project.created_by_id != request.user.id:
        return HttpResponseBadRequest("Non autorisé")

    new_state = request.POST.get('completed') == '1'
    item.completed = new_state
    update_fields = ['completed']
    if hasattr(item, 'completed_at'):
        item.completed_at = timezone.now() if new_state else None
        update_fields.append('completed_at')
    item.save(update_fields=update_fields)

    messages.success(request, "Étape mise à jour.")
    return redirect('project_detail', pk=item.project_id)

@login_required
def project_checklist_pdf_view(request, pk):
    tech = _sync_user_and_technician_from_directory(request.user)
    project = get_object_or_404(Project, pk=pk) if getattr(tech, 'is_manager', False) else get_object_or_404(
        Project, Q(pk=pk) & (Q(technician=tech) | Q(created_by=request.user))
    )

    items = (ChecklistItem.objects
             .filter(project=project)
             .prefetch_related('notes', 'images')
             .order_by('order', 'id'))

    html = render_to_string('checklist_pdf.html', {
        'project': project,
        'items': items,
        'generated_at': timezone.now(),
        'user': request.user,
    })

    pdf_io = io.BytesIO()
    pisa_status = pisa.CreatePDF(io.BytesIO(html.encode('utf-8')), dest=pdf_io)
    if pisa_status.err:
        return HttpResponseBadRequest("Échec de génération du PDF")

    pdf_io.seek(0)
    filename = f"Checklist_{project.project_number}.pdf" if project.project_number else "Checklist.pdf"
    return FileResponse(pdf_io, filename=filename, content_type='application/pdf')

# --- Profile (kept for URL import) ---
@login_required
def profile_view(request):
    tech, _ = Technician.objects.get_or_create(user=request.user, defaults={'role': 'Technicien'})

    assigned_qs = Project.objects.filter(technician=tech)
    created_qs = Project.objects.filter(created_by=request.user)

    total = assigned_qs.count()
    pending = assigned_qs.filter(status='pending').count()
    doing = assigned_qs.filter(status='in_progress').count()
    done = assigned_qs.filter(status='completed').count()

    on_time = (
        assigned_qs.filter(status='completed')
        .annotate(_done_date=TruncDate('updated_at'))
        .filter(_done_date__lte=F('date'))
        .count()
    )
    on_time_rate = int((on_time / done) * 100) if done else 0

    assigned_list = list(assigned_qs[:500])
    completion_avg = int(sum(p.completion_percentage for p in assigned_list) / total) if total else 0

    recent_assigned = assigned_qs.select_related('technician').order_by('-created_at')[:10]
    recent_created  = created_qs.select_related('technician').order_by('-created_at')[:10]

    product_counts = (
        assigned_qs.values('product')
        .annotate(c=Count('id'))
        .order_by('-c')
    )

    context = {
        'technician': tech,
        'total': total,
        'pending': pending,
        'doing': doing,
        'done': done,
        'on_time_rate': on_time_rate,
        'completion_avg': completion_avg,
        'recent_assigned': recent_assigned,
        'recent_created': recent_created,
        'product_counts': product_counts,
    }
    return render(request, 'profile.html', context)
