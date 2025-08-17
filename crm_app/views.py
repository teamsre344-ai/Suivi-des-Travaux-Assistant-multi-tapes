from datetime import date, datetime, timedelta
import io
import json
import os

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.staticfiles import finders
from django.core.paginator import Paginator
from django.db.models import (
    Q, F, Count, Avg, DurationField, ExpressionWrapper, Case, When, IntegerField
)
from django.db.models.functions import TruncMonth, TruncDate, TruncYear, Coalesce
from django.http import HttpResponse, FileResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.http import require_POST

from xhtml2pdf import pisa  # pip install xhtml2pdf

from .forms import LoginForm, ProjectForm, ChecklistJSONUploadForm, ChecklistItemUpdateForm
from .models import (
    ChecklistItem,
    Project,
    Technician,
    TimelineEntry,
    ChecklistItemImage,
    ChecklistItemNote,
    ChecklistTemplate,
)


# ------------------ Auth ------------------
def login_view(request):
    if request.user.is_authenticated:
        return redirect('home')

    form = LoginForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        ident = form.cleaned_data['identifier'].strip()
        pwd = form.cleaned_data['password']

        username = ident
        try:
            user_obj = User.objects.get(email__iexact=ident)
            username = user_obj.username
        except User.DoesNotExist:
            pass

        user = authenticate(request, username=username, password=pwd)
        if user:
            login(request, user)
            messages.success(request, 'Connexion réussie.')
            return redirect('home')
        messages.error(request, "Identifiants invalides.")
    return render(request, 'login.html', {'form': form})


@login_required
def logout_view(request):
    logout(request)
    return redirect('login')


# ------------------ Helpers ------------------
def _pct_change(current: int, prev: int) -> float:
    if prev == 0:
        return 100.0 if current > 0 else 0.0
    return round((current - prev) * 100.0 / prev, 1)


# ------------------ Dashboard ------------------
@login_required
def home_view(request):
    # Profile
    tech, _ = Technician.objects.get_or_create(user=request.user, defaults={'role': 'Technicien'})
    is_manager = tech.is_manager

    # Scope
    projects = Project.objects.all() if is_manager else Project.objects.filter(technician=tech)

    # Headline counts
    total_projects = projects.count()
    pending_projects = projects.filter(status='pending').count()
    in_progress_projects = projects.filter(status='in_progress').count()
    completed_projects = projects.filter(status='completed').count()

    # Trends (week over week)
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

    # Product distribution & recent
    product_counts = projects.values('product').annotate(c=Count('id')).order_by('-c')
    recent_projects = projects.select_related('technician').order_by('-created_at')[:8]

    # -----------------------------
    # PERFORMANCE DIAGRAM (12 mo.)
    # -----------------------------
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

    # Recent KPIs used in the header of the card
    last30_created = projects.filter(created_at__gte=now - timedelta(days=30)).count()
    last30_completed_qs = projects.filter(status='completed', updated_at__gte=now - timedelta(days=30))
    last30_completed = last30_completed_qs.count()

    # On-time rate for last 90 days
    last90_completed_qs = projects.filter(status='completed', updated_at__gte=now - timedelta(days=90))
    last90_on_time = (last90_completed_qs
                      .annotate(done_date=TruncDate('updated_at'))
                      .filter(done_date__lte=F('date'))
                      .count())
    on_time_rate_90 = int(last90_on_time * 100 / last90_completed_qs.count()) if last90_completed_qs.exists() else 0

    # Average lead time (created -> completed) in last 90 days
    dur_expr = ExpressionWrapper(F('updated_at') - F('created_at'), output_field=DurationField())
    avg_lead_td = (last90_completed_qs.annotate(dur=dur_expr).aggregate(avg=Avg('dur'))['avg']) or timedelta(0)
    avg_lead_days_90 = round(avg_lead_td.total_seconds() / 86400, 1) if avg_lead_td else 0.0

    # -----------------------------
    # NEW: donut data (work_type)
    # -----------------------------
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

        # diagram + KPIs
        'diagram_bars': diagram_bars,
        'last30_created': last30_created,
        'last30_completed': last30_completed,
        'on_time_rate_90': on_time_rate_90,
        'avg_lead_days_90': avg_lead_days_90,

        # NEW donut arrays
        'worktype_labels': worktype_labels,
        'worktype_values': worktype_values,
    }
    return render(request, 'home.html', context)


# in views.py (below other views)
@login_required
def analytics_view(request):
    tech, _ = Technician.objects.get_or_create(user=request.user, defaults={'role': 'Technicien'})
    is_manager = tech.is_manager
    projects = Project.objects.all() if is_manager else Project.objects.filter(technician=tech)
    return render(request, "analytics.html", {"technician": tech, "total": projects.count()})


# ------------------ Project list ------------------
@login_required
def project_list_view(request):
    tech, _ = Technician.objects.get_or_create(user=request.user, defaults={'role': 'Technicien'})

    # Base queryset: managers see all, others see only assigned
    qs = Project.objects.all() if tech.is_manager else Project.objects.filter(technician=tech)

    # --- Read filters ---
    status = (request.GET.get('status') or '').strip()
    environment = (request.GET.get('environment') or '').strip()
    product = (request.GET.get('product') or '').strip()
    q = (request.GET.get('q') or '').strip()
    # NEW: donut click support
    work_type = (request.GET.get('work_type') or '').strip()

    created_by_me = request.GET.get('created_by_me') == 'on'
    assigned_to_me = request.GET.get('assigned_to_me') == 'on'

    date_from = (request.GET.get('date_from') or '').strip()
    date_to = (request.GET.get('date_to') or '').strip()

    sort_key = (request.GET.get('sort') or 'created_desc').strip()
    per_page = int(request.GET.get('per_page') or 10)
    per_page_choices = [10, 20, 50, 100]

    # --- Apply filters ---
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

    # Date range (inclusive)
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

    # Sorting
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

    # CSV export (honors filters)
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

    # Pagination
    paginator = Paginator(qs.select_related('technician').only(
        'id', 'project_number', 'title', 'client_name', 'product', 'environment',
        'status', 'created_at', 'date', 'technician__user__first_name', 'technician__user__last_name'
    ), per_page)
    page_obj = paginator.get_page(request.GET.get('page') or 1)

    # Status counts for quick chips
    status_counts = Project.objects.values('status').annotate(c=Count('id'))
    status_map = {s['status']: s['c'] for s in status_counts}

    # Product choices (distinct values actually in DB)
    products = list(Project.objects.order_by().values_list('product', flat=True).distinct())

    context = {
        'technician': tech,
        'projects': page_obj,
        'page_obj': page_obj,
        'paginator': paginator,

        # keep filters in template
        'status': status,
        'environment': environment,
        'product': product,
        'work_type': work_type,  # NEW
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
    tech, _ = Technician.objects.get_or_create(user=request.user, defaults={'role': 'Technicien'})
    base = Project.objects.all() if tech.is_manager else Project.objects.filter(technician=tech)

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
    tech, _ = Technician.objects.get_or_create(user=request.user, defaults={'role': 'Technicien'})

    # Optional ruleset (by name) passed as ?ruleset=<name>
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
            p.technician = tech if not tech.is_manager else tech  # managers can still own it
            env_label = 'Test' if p.environment == 'test' else 'Production'
            p.title = f"{env_label} — {p.client_name} — {p.product} — {p.project_number}"

            # Link the ruleset if provided
            if ruleset:
                p.ruleset = ruleset
                if ruleset.default_checklist:
                    p.checklist_data = ruleset.default_checklist

            # If no ruleset checklist, create a sensible default
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

            # Materialize checklist items
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
        # Pre-fill form from ruleset if provided
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
    tech, _ = Technician.objects.get_or_create(user=request.user, defaults={'role': 'Technicien'})
    p = get_object_or_404(Project, pk=pk) if tech.is_manager else get_object_or_404(
        Project, Q(pk=pk) & (Q(technician=tech) | Q(created_by=request.user))
    )
    is_creator = (p.created_by_id == request.user.id)
    return render(request, 'project_detail.html', {'project': p, 'technician': tech, 'is_creator': is_creator})


# ------------------ Profile ------------------
@login_required
def profile_view(request):
    tech, _ = Technician.objects.get_or_create(user=request.user, defaults={'role': 'Technicien'})

    # Projects the user is assigned to (as technician)
    assigned_qs = Project.objects.filter(technician=tech)

    # Projects the user created
    created_qs = Project.objects.filter(created_by=request.user)

    total = assigned_qs.count()
    pending = assigned_qs.filter(status='pending').count()
    doing = assigned_qs.filter(status='in_progress').count()
    done = assigned_qs.filter(status='completed').count()

    # On-time: completed where last update date <= scheduled project "date"
    on_time = (
        assigned_qs.filter(status='completed')
        .annotate(_done_date=TruncDate('updated_at'))
        .filter(_done_date__lte=F('date'))
        .count()
    )
    on_time_rate = int((on_time / done) * 100) if done else 0

    # Average checklist completion (compute in Python since it's a property)
    assigned_list = list(assigned_qs[:500])  # safety cap
    completion_avg = int(sum(p.completion_percentage for p in assigned_list) / total) if total else 0

    recent_assigned = assigned_qs.select_related('technician').order_by('-created_at')[:10]
    recent_created = created_qs.select_related('technician').order_by('-created_at')[:10]

    # Product mix for the user
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


# ------------------ Team dashboard ------------------
@login_required
def team_dashboard_view(request):
    tech, _ = Technician.objects.get_or_create(user=request.user, defaults={'role': 'Technicien'})
    if not tech.is_manager:
        messages.error(request, 'Accès réservé aux managers.')
        return redirect('home')

    # Aggregate counts per technician
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

    # Build a lightweight structure with recent projects + completion %
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
    tech, _ = Technician.objects.get_or_create(user=request.user, defaults={'role': 'Technicien'})
    # managers can see all; technicians see their own
    if tech.is_manager:
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

    # Enforce sequence at the view level too (friendlier message)
    if phase == 'execution' and new_state in ('in_progress', 'completed') and p.preparation_phase != 'completed':
        messages.error(request, "Terminez la préparation avant de démarrer l'exécution.")
        return redirect('project_detail', pk=p.pk)
    if phase == 'validation' and new_state in ('in_progress', 'completed') and p.execution_phase != 'completed':
        messages.error(request, "Terminez l'exécution avant de démarrer la validation.")
        return redirect('project_detail', pk=p.pk)

    # Apply change
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


# ------------------ GEO: full overview page ------------------
@login_required
def geo_overview(request):
    """Interactive map + 10-year analytics."""
    ten_years_start = date(timezone.now().year - 10, 1, 1)

    base = Project.objects.filter(date__gte=ten_years_start)

    # Markers (skip if no coords)
    markers = list(
        base.exclude(latitude__isnull=True, longitude__isnull=True)
            .values('id', 'project_number', 'client_name', 'product',
                    'work_type', 'status', 'date',
                    'site_city', 'site_region', 'site_country',
                    'latitude', 'longitude')
    )

    # Totaux par région (10 ans)
    by_region = (
        base.values('site_region')
            .exclude(site_region='')
            .annotate(total=Count('id'))
            .order_by('-total')
    )

    # Annuel (10 ans)
    by_year = (
        base.annotate(y=TruncYear('date'))
            .values('y')
            .annotate(total=Count('id'))
            .order_by('y')
    )

    # Par type de travaux (work_type) dans chaque région (top 8 régions)
    top_regions = [r['site_region'] for r in by_region[:8]]
    by_type_region = (
        base.filter(site_region__in=top_regions)
            .values('site_region', 'work_type')
            .annotate(total=Count('id'))
            .order_by('site_region', '-total')
    )

    context = {
        'markers': markers,
        'by_region': list(by_region),
        'by_year': list(by_year),
        'by_type_region': list(by_type_region),
        'ten_years_start': ten_years_start,
    }
    return render(request, 'geo_overview.html', context)


# =====================================================================
# ===============  CHECKLIST: JSON import / notes / images  ===========
# =====================================================================

@login_required
@require_POST
def checklist_import_view(request, pk):
    """Attach a JSON checklist to a project (replaces current items)."""
    tech, _ = Technician.objects.get_or_create(user=request.user, defaults={'role': 'Technicien'})
    project = get_object_or_404(Project, pk=pk) if tech.is_manager else get_object_or_404(
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

    # Wipe existing list and rebuild in order
    ChecklistItem.objects.filter(project=project).delete()
    for i, item in enumerate(items):
        label = (item.get('label') or '').strip() if isinstance(item, dict) else str(item).strip()
        if not label:
            label = f"Étape {i+1}"
        ChecklistItem.objects.create(project=project, label=label, order=i)

    # Keep a JSON copy on the Project (optional)
    project.checklist_data = {'items': [{'label': (x.get('label') if isinstance(x, dict) else str(x)) or ''} for x in items]}
    project.save(update_fields=['checklist_data', 'updated_at'])

    messages.success(request, f"Checklist importée: {len(items)} étapes.")
    return redirect('project_detail', pk=project.pk)


@login_required
@require_POST
def checklist_item_add_note_view(request, item_id):
    """Add a comment and optional multiple images to a checklist item."""
    tech, _ = Technician.objects.get_or_create(user=request.user, defaults={'role': 'Technicien'})
    item = get_object_or_404(ChecklistItem, pk=item_id)

    # Authorization: owner/assignee or manager
    if not tech.is_manager and item.project.technician_id != tech.id and item.project.created_by_id != request.user.id:
        return HttpResponseBadRequest("Non autorisé")

    form = ChecklistItemUpdateForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "Formulaire invalide.")
        return redirect('project_detail', pk=item.project_id)

    text = form.cleaned_data.get('text', '').strip()
    if text:
        ChecklistItemNote.objects.create(item=item, author=request.user, text=text)

    files = request.FILES.getlist('images')
    for f in files:
        if f:  # basic guard
            ChecklistItemImage.objects.create(item=item, image=f)

    messages.success(request, "Note/Images ajoutées.")
    return redirect('project_detail', pk=item.project_id)


@login_required
@require_POST
def checklist_item_toggle_view(request, item_id):
    """Toggle a checklist item completed flag."""
    tech, _ = Technician.objects.get_or_create(user=request.user, defaults={'role': 'Technicien'})
    item = get_object_or_404(ChecklistItem, pk=item_id)

    if not tech.is_manager and item.project.technician_id != tech.id and item.project.created_by_id != request.user.id:
        return HttpResponseBadRequest("Non autorisé")

    new_state = request.POST.get('completed') == '1'
    item.completed = new_state
    update_fields = ['completed']
    # Optionally support a completed_at field if your model has it
    if hasattr(item, 'completed_at'):
        item.completed_at = timezone.now() if new_state else None
        update_fields.append('completed_at')
    item.save(update_fields=update_fields)

    messages.success(request, "Étape mise à jour.")
    return redirect('project_detail', pk=item.project_id)


# --- Helper for xhtml2pdf to resolve STATIC/MEDIA paths
def _pisa_link_callback(uri, rel):
    """
    Convert HTML URIs (e.g., /static/... or /media/...) into absolute file system paths
    so xhtml2pdf can embed images and assets.
    """
    # MEDIA files
    if settings.MEDIA_URL and uri.startswith(settings.MEDIA_URL):
        path = os.path.join(settings.MEDIA_ROOT, uri.replace(settings.MEDIA_URL, "", 1))
        return path

    # STATIC files (use staticfiles finders)
    if settings.STATIC_URL and uri.startswith(settings.STATIC_URL):
        path = finders.find(uri.replace(settings.STATIC_URL, "", 1))
        if path:
            return path

    # Absolute URI (http/https) – let pisa try to fetch as-is
    return uri


@login_required
def project_checklist_pdf_view(request, pk):
    """Export the project's checklist (with comments & images) to a PDF."""
    tech, _ = Technician.objects.get_or_create(user=request.user, defaults={'role': 'Technicien'})
    project = get_object_or_404(Project, pk=pk) if tech.is_manager else get_object_or_404(
        Project, Q(pk=pk) & (Q(technician=tech) | Q(created_by=request.user))
    )

    items = (ChecklistItem.objects
             .filter(project=project)
             .prefetch_related('notes', 'images')
             .order_by('order', 'id'))

    # Render HTML to PDF
    html = render_to_string('checklist_pdf.html', {
        'project': project,
        'items': items,
        'generated_at': timezone.now(),
        'user': request.user,
    })

    pdf_io = io.BytesIO()
    pisa_status = pisa.CreatePDF(src=html, dest=pdf_io, link_callback=_pisa_link_callback, encoding='utf-8')
    if pisa_status.err:
        return HttpResponseBadRequest("Échec de génération du PDF")

    pdf_io.seek(0)
    filename = f"Checklist_{project.project_number}.pdf" if project.project_number else "Checklist.pdf"
    return FileResponse(pdf_io, filename=filename, content_type='application/pdf')
