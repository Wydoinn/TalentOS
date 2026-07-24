import { Component, inject, OnInit, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { Router, RouterLink, ActivatedRoute } from '@angular/router';
import { DataService, Candidate, CandidateProfileAI, type AssessmentReportSummary } from '../../core/data.service';

@Component({
  selector: 'app-candidate-profile',
  standalone: true,
  imports: [MatIconModule, RouterLink],
  template: `
    <div class="space-y-6 animate-in">
      <!-- Back Navigation -->
      <a routerLink="/candidates" class="inline-flex items-center gap-2 text-sm font-medium text-slate-500 transition-colors hover:text-primary-700">
        <mat-icon class="text-[20px]">arrow_back</mat-icon>
        Back to Candidates
      </a>

      @if (dataService.errorMessage()) {
        <div class="text-sm text-red-600 bg-red-50 border border-red-100 rounded-xl px-4 py-3">
          {{ dataService.errorMessage() }}
        </div>
      }

      @if (profileLoading()) {
        <div class="text-center py-12 text-gray-500">
          Loading candidate profile...
        </div>
      } @else if (candidate) {
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <!-- Left Column: Profile Info -->
          <div class="lg:col-span-1 space-y-6">
            <!-- Main Profile Card -->
            <div class="rounded-2xl border border-rose-100 bg-white p-6 text-center shadow-sm">
              <img [src]="candidate.avatar" [alt]="candidate.name" class="mx-auto mb-4 h-24 w-24 rounded-full bg-rose-50" />
              <h1 class="text-xl font-bold text-gray-900">{{ candidate.name }}</h1>
              <p class="text-gray-500 text-sm mb-4">{{ candidate.role }}</p>

              <div class="flex justify-center gap-2 mb-6">
                @if (candidate.experience && candidate.experience !== 'Under review') {
                  <span class="inline-flex items-center gap-1 rounded-full bg-rose-50 px-2.5 py-1 text-xs font-medium text-rose-700">
                    <mat-icon class="text-[14px]">work_history</mat-icon> {{ candidate.experience }}
                  </span>
                }
                @if (candidate.source) {
                  <span class="inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium"
                    [class]="candidate.source === 'internal' ? 'bg-primary-50 text-primary-700' : 'bg-rose-50 text-rose-700'">
                    <mat-icon class="text-[14px]">inventory_2</mat-icon> {{ candidate.source }}
                  </span>
                }
                @if (jobTitle()) {
                  <span class="inline-flex items-center gap-1 rounded-full bg-primary-50 px-2.5 py-1 text-xs font-medium text-primary-700">
                    <mat-icon class="text-[14px]">work</mat-icon> {{ jobTitle() }}
                  </span>
                }
              </div>

              <div class="flex gap-3">
                @if (candidate.status === 'Shortlisted') {
                  <button (click)="updateStatus('Interview')" [disabled]="statusUpdating()" class="flex-1 rounded-xl bg-primary-700 py-2 text-sm font-medium text-white shadow-sm shadow-primary-500/30 transition-colors hover:bg-primary-800 disabled:cursor-not-allowed disabled:opacity-50">
                    Send L0 Invite
                  </button>
                } @else if (candidate.status === 'Interview') {
                  <button class="flex-1 cursor-not-allowed rounded-xl bg-slate-100 py-2 text-sm font-medium text-slate-500">
                    Invite Sent
                  </button>
                } @else {
                  <button (click)="updateStatus('Shortlisted')" [disabled]="statusUpdating()" class="flex-1 rounded-xl bg-primary-600 py-2 text-sm font-medium text-white shadow-sm shadow-primary-500/30 transition-colors hover:bg-primary-700 disabled:cursor-not-allowed disabled:opacity-50">
                    Shortlist
                  </button>
                }

                <a [href]="emailLink()" class="rounded-xl border border-rose-200 p-2 text-rose-700 transition-colors hover:bg-rose-50">
                  <mat-icon class="text-[20px]">mail_outline</mat-icon>
                </a>
                <button (click)="updateStatus('Rejected')" [disabled]="statusUpdating()" class="rounded-xl border border-red-200 p-2 text-red-600 transition-colors hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50">
                  <mat-icon class="text-[20px]">close</mat-icon>
                </button>
              </div>
            </div>

            <!-- Contact Info -->
            <div class="rounded-2xl border border-rose-100 bg-white p-6 shadow-sm">
              <h2 class="text-sm font-semibold text-gray-900 uppercase tracking-wider mb-4">Contact Information</h2>
              <div class="space-y-4">
                <div class="flex items-center gap-3 text-sm">
                  <div class="flex h-8 w-8 items-center justify-center rounded-full bg-rose-50 text-rose-700">
                    <mat-icon class="text-[18px]">mail</mat-icon>
                  </div>
                  <span class="text-gray-700">{{ primaryEmail() || 'Email pending' }}</span>
                </div>
                <div class="flex items-center gap-3 text-sm">
                  <div class="flex h-8 w-8 items-center justify-center rounded-full bg-rose-50 text-rose-700">
                    <mat-icon class="text-[18px]">phone</mat-icon>
                  </div>
                  @if (primaryPhone() && primaryPhone() !== 'Pending') {
                    <a [href]="phoneLink()" class="text-primary-600 hover:underline">{{ primaryPhone() }}</a>
                  } @else {
                    <span class="text-gray-700">Phone pending</span>
                  }
                </div>
              </div>
            </div>
          </div>

          <!-- Right Column: Details & AI Insights -->
          <div class="lg:col-span-2 space-y-6">
            <!-- AI Match Score & Insights -->
            <div class="rounded-2xl border border-rose-100 bg-gradient-to-br from-rose-50 to-white p-6 shadow-sm">
              <div class="flex items-start justify-between mb-6">
                <div>
                  <h2 class="text-lg font-semibold text-gray-900 flex items-center gap-2">
                    <mat-icon class="text-primary-500">auto_awesome</mat-icon>
                    AI Match Analysis
                  </h2>
                  <p class="text-sm text-gray-600 mt-1">For role: <span class="font-medium text-gray-900">{{ candidate.role }}</span></p>
                </div>
                <div class="text-right">
                  <span class="text-3xl font-bold text-primary-700">{{ candidate.matchScore }}%</span>
                  <p class="text-xs font-medium text-primary-700 uppercase tracking-wider">
                    {{ candidate.matchScore >= 90 ? 'Excellent Match' : candidate.matchScore >= 80 ? 'Good Match' : 'Fair Match' }}
                  </p>
                </div>
              </div>

              @if (aiSummaryText()) {
                <div class="mb-5 rounded-xl border border-primary-100 bg-white/70 px-4 py-3">
                  <p class="text-xs font-semibold uppercase tracking-wider text-primary-700 mb-1">AI Summary</p>
                  <p class="text-sm text-gray-700">{{ aiSummaryText() }}</p>
                </div>
              }

              <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <h3 class="text-sm font-semibold text-gray-900 mb-3 flex items-center gap-2">
                    <mat-icon class="text-primary-600 text-[18px]">check_circle</mat-icon> Key Strengths
                  </h3>
                  <ul class="space-y-2">
                    @for (item of strengthHighlights(); track item) {
                      <li class="text-sm text-gray-700 flex items-start gap-2">
                        <span class="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-primary-600"></span>
                        {{ item }}
                      </li>
                    }
                  </ul>
                </div>
                <div>
                  <h3 class="text-sm font-semibold text-gray-900 mb-3 flex items-center gap-2">
                    <mat-icon class="text-rose-500 text-[18px]">info</mat-icon> Areas for Growth
                  </h3>
                  <ul class="space-y-2">
                    @for (item of growthHighlights(); track item) {
                      <li class="text-sm text-gray-700 flex items-start gap-2">
                        <span class="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-rose-500"></span>
                        {{ item }}
                      </li>
                    }
                  </ul>
                </div>
              </div>

              @if (aiSuggestions().length > 0 || aiIssues().length > 0) {
                <div class="mt-5 grid grid-cols-1 md:grid-cols-2 gap-4">
                  @if (aiSuggestions().length > 0) {
                    <div class="rounded-xl border border-rose-200 bg-rose-50/70 p-4">
                      <p class="mb-2 text-xs font-semibold uppercase tracking-wider text-rose-700">Interview Suggestions</p>
                      <div class="space-y-1.5">
                        @for (item of aiSuggestions(); track item) {
                          <p class="text-sm text-rose-900">{{ item }}</p>
                        }
                      </div>
                    </div>
                  }

                  @if (aiIssues().length > 0) {
                    <div class="rounded-xl border border-red-100 bg-red-50/80 p-4">
                      <p class="mb-2 text-xs font-semibold uppercase tracking-wider text-red-700">Potential Gaps</p>
                      <div class="space-y-1.5">
                        @for (item of aiIssues(); track item) {
                          <p class="text-sm text-red-900">{{ item }}</p>
                        }
                      </div>
                    </div>
                  }
                </div>
              }
            </div>

            <!-- Candidate Snapshot -->
            <div class="rounded-2xl border border-rose-100 bg-white p-6 shadow-sm">
              <h2 class="text-lg font-semibold text-gray-900 mb-6">Candidate Snapshot</h2>
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div class="rounded-xl border border-rose-100 p-4">
                  <p class="text-xs text-gray-500 uppercase tracking-wider">Current Stage</p>
                  <p class="text-sm font-semibold text-gray-900 mt-1">{{ candidate.status }}</p>
                </div>
                <div class="rounded-xl border border-rose-100 p-4">
                  <p class="text-xs text-gray-500 uppercase tracking-wider">Applied</p>
                  <p class="text-sm font-semibold text-gray-900 mt-1">{{ candidate.appliedAt }}</p>
                </div>
                <div class="rounded-xl border border-rose-100 p-4">
                  <p class="text-xs text-gray-500 uppercase tracking-wider">Resume Source</p>
                  <p class="text-sm font-semibold text-gray-900 mt-1">{{ candidate.source || aiProfile()?.source || 'Under review' }}</p>
                </div>
                <div class="rounded-xl border border-rose-100 p-4">
                  <p class="text-xs text-gray-500 uppercase tracking-wider">Experience</p>
                  <p class="text-sm font-semibold text-gray-900 mt-1">{{ candidate.experience }}</p>
                </div>
                <div class="rounded-xl border border-rose-100 p-4">
                  <p class="text-xs text-gray-500 uppercase tracking-wider">Education</p>
                  <p class="text-sm font-semibold text-gray-900 mt-1">{{ candidate.education }}</p>
                </div>
              </div>
            </div>

            <div class="rounded-2xl border border-rose-100 bg-white p-6 shadow-sm">
              <div class="flex items-start justify-between gap-4">
                <div>
                  <h2 class="text-lg font-semibold text-gray-900">Assessment Status</h2>
                  <p class="mt-1 text-sm text-gray-500">Track the latest L0 session and jump into the saved report.</p>
                </div>
                @if (latestAssessmentSummary()?.reportAvailable) {
                  <button
                    type="button"
                    (click)="openAssessmentReport()"
                    class="rounded-xl bg-primary-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-primary-700"
                  >
                    Open Report
                  </button>
                }
              </div>

              @if (latestAssessmentSummary(); as assessment) {
                <div class="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-3">
                  <div class="rounded-xl border border-rose-100 p-4">
                    <p class="text-xs text-gray-500 uppercase tracking-wider">Session</p>
                    <p class="mt-1 text-sm font-semibold text-gray-900">{{ humanizeStatus(assessment.sessionStatus) }}</p>
                  </div>
                  <div class="rounded-xl border border-rose-100 p-4">
                    <p class="text-xs text-gray-500 uppercase tracking-wider">Decision</p>
                    <p class="mt-1 text-sm font-semibold text-gray-900">{{ assessment.decision || 'Pending' }}</p>
                  </div>
                  <div class="rounded-xl border border-rose-100 p-4">
                    <p class="text-xs text-gray-500 uppercase tracking-wider">Overall Score</p>
                    <p class="mt-1 text-sm font-semibold text-gray-900">{{ formatAssessmentScore(assessment) }}</p>
                  </div>
                </div>

                @if (assessment.summary) {
                  <div class="mt-4 rounded-xl border border-rose-100 bg-rose-50/60 p-4">
                    <p class="text-xs font-semibold uppercase tracking-wider text-rose-700">Latest Summary</p>
                    <p class="mt-2 text-sm text-gray-700">{{ assessment.summary }}</p>
                  </div>
                }
              } @else {
                <div class="mt-5 rounded-xl border border-dashed border-rose-200 bg-rose-50/60 px-4 py-6 text-center text-sm text-gray-500">
                  No assessment session has been recorded for this candidate yet.
                </div>
              }
            </div>

            <!-- Skills -->
            <div class="rounded-2xl border border-rose-100 bg-white p-6 shadow-sm">
              <h2 class="text-lg font-semibold text-gray-900 mb-4">Skills</h2>
              <div class="flex flex-wrap gap-2">
                @for (skill of candidate.skills; track skill) {
                  <span class="rounded-lg bg-rose-50 px-3 py-1.5 text-sm font-medium text-rose-700">{{ skill }}</span>
                }
              </div>
            </div>

            @if (profileSignals().length > 0) {
              <div class="rounded-2xl border border-rose-100 bg-white p-6 shadow-sm">
                <h2 class="text-lg font-semibold text-gray-900 mb-4">AI Match Signals</h2>
                <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  @for (signal of profileSignals(); track signal.label) {
                    <div class="rounded-xl border border-rose-100 p-4">
                      <p class="text-xs uppercase tracking-wider text-gray-500">{{ signal.label }}</p>
                      <p class="mt-1 text-sm font-semibold text-gray-900">{{ signal.value }}</p>
                    </div>
                  }
                </div>
              </div>
            }

            @if (experienceTimeline().length > 0) {
              <div class="rounded-2xl border border-rose-100 bg-white p-6 shadow-sm">
                <h2 class="text-lg font-semibold text-gray-900 mb-4">Experience Timeline</h2>
                <div class="space-y-4">
                  @for (item of experienceTimeline(); track experienceTrack(item)) {
                    <div class="rounded-xl border border-rose-100 p-4">
                      <p class="text-sm font-semibold text-gray-900">{{ experienceHeadline(item) }}</p>
                      <p class="mt-1 text-xs text-gray-500">{{ experienceMeta(item) }}</p>
                      @if (experienceSummary(item)) {
                        <p class="mt-2 text-sm text-gray-700">{{ experienceSummary(item) }}</p>
                      }
                    </div>
                  }
                </div>
              </div>
            }

            @if (projects().length > 0 || educationHistory().length > 0) {
              <div class="grid grid-cols-1 gap-6 xl:grid-cols-2">
                @if (projects().length > 0) {
                  <div class="rounded-2xl border border-rose-100 bg-white p-6 shadow-sm">
                    <h2 class="text-lg font-semibold text-gray-900 mb-4">Projects</h2>
                    <div class="space-y-4">
                      @for (project of projects(); track projectTrack(project)) {
                        <div class="rounded-xl border border-rose-100 p-4">
                          <p class="text-sm font-semibold text-gray-900">{{ projectHeadline(project) }}</p>
                          @if (projectSummary(project)) {
                            <p class="mt-2 text-sm text-gray-700">{{ projectSummary(project) }}</p>
                          }
                        </div>
                      }
                    </div>
                  </div>
                }

                @if (educationHistory().length > 0) {
                  <div class="rounded-2xl border border-rose-100 bg-white p-6 shadow-sm">
                    <h2 class="text-lg font-semibold text-gray-900 mb-4">Education</h2>
                    <div class="space-y-4">
                      @for (item of educationHistory(); track educationTrack(item)) {
                        <div class="rounded-xl border border-rose-100 p-4">
                          <p class="text-sm font-semibold text-gray-900">{{ educationHeadline(item) }}</p>
                          <p class="mt-1 text-xs text-gray-500">{{ educationMeta(item) }}</p>
                        </div>
                      }
                    </div>
                  </div>
                }
              </div>
            }
          </div>
        </div>
      } @else {
        <div class="text-center py-12 text-gray-500">
          Candidate not found.
        </div>
      }
    </div>
  `
})
export class CandidateProfileComponent implements OnInit {
  dataService = inject(DataService);
  route = inject(ActivatedRoute);
  router = inject(Router);

  candidate: Candidate | null = null;
  aiProfile = signal<CandidateProfileAI | null>(null);
  latestAssessmentSummary = signal<AssessmentReportSummary | null>(null);
  profileLoading = signal(true);
  statusUpdating = signal(false);

  ngOnInit() {
    void this.initialize();
  }

  private async initialize(): Promise<void> {
    this.profileLoading.set(true);

    if (this.dataService.jobs().length === 0) {
      await this.dataService.loadJobs();
    }

    const rawId = this.route.snapshot.paramMap.get('id');
    const jobId = this.route.snapshot.queryParamMap.get('jobId');
    const matchId = this.route.snapshot.queryParamMap.get('matchId');

    let resolved: Candidate | null = null;
    if (rawId) {
      const candidateId = this.decodeCandidateId(rawId);
      resolved = await this.dataService.getCandidateById(candidateId, {jobId, matchId});

      if (!resolved && candidateId !== rawId) {
        resolved = await this.dataService.getCandidateById(rawId, {jobId, matchId});
      }
    }

    if (!resolved && matchId) {
      resolved = await this.dataService.getCandidateById(matchId, {jobId, matchId});
    }

    this.candidate = resolved;

    if (resolved?.jobId && resolved.matchId) {
      const profile = await this.dataService.loadCandidateProfileAI(
        resolved.jobId,
        resolved.matchId,
        resolved.id,
      );
      this.aiProfile.set(profile);
    } else {
      this.aiProfile.set(null);
    }

    if (resolved?.jobId && resolved.email) {
      try {
        const summaries = await this.dataService.getAssessmentReportSummaries({
          jobId: resolved.jobId,
          candidateEmail: resolved.email,
        });
        this.latestAssessmentSummary.set(summaries[0] ?? null);
      } catch {
        this.latestAssessmentSummary.set(null);
      }
    } else {
      this.latestAssessmentSummary.set(null);
    }

    this.profileLoading.set(false);
  }

  async updateStatus(status: 'Applied' | 'Shortlisted' | 'Interview' | 'Rejected') {
    if (this.candidate) {
      try {
        this.statusUpdating.set(true);
        if (status === 'Interview' && this.candidate.jobId) {
          await this.dataService.inviteCandidate(this.candidate.jobId, {
            email: this.primaryEmail(),
            name: this.candidate.name,
          });
        }
        await this.dataService.updateCandidateStatus(this.candidate.id, status);
        this.candidate = this.dataService.candidates().find(c => c.id === this.candidate!.id) || null;
      } finally {
        this.statusUpdating.set(false);
      }
    }
  }

  emailLink(): string {
    const email = this.primaryEmail();
    return email ? `mailto:${email}` : 'mailto:';
  }

  phoneLink(): string {
    const raw = this.primaryPhone();
    const sanitized = raw.replace(/[^+\d]/g, '');
    return sanitized ? `tel:${sanitized}` : 'tel:';
  }

  private decodeCandidateId(candidateId: string): string {
    try {
      return decodeURIComponent(candidateId);
    } catch {
      return candidateId;
    }
  }

  async openAssessmentReport(): Promise<void> {
    const sessionId = this.latestAssessmentSummary()?.assessmentSessionId;
    if (!sessionId) {
      return;
    }

    await this.router.navigate(['/reports'], {
      queryParams: {sessionId},
    });
  }

  humanizeStatus(value: string): string {
    return value.replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase());
  }

  formatAssessmentScore(summary: AssessmentReportSummary): string {
    return summary.overallScore !== null ? `${Math.round(summary.overallScore)}%` : 'Not available yet';
  }

  jobTitle(): string | null {
    const candidate = this.candidate;
    if (!candidate?.jobId) {
      return null;
    }
    return this.dataService.jobs().find((job) => job.id === candidate.jobId)?.title ?? null;
  }

  strengthHighlights(): string[] {
    const aiReasons = this.aiReasons();
    if (aiReasons.length > 0) {
      return aiReasons.slice(0, 4);
    }

    const candidate = this.candidate;
    if (!candidate) {
      return [];
    }

    const strengths = candidate.skills.slice(0, 4).map((skill) => `Strong evidence of ${skill}.`);
    if (strengths.length > 0) {
      return strengths;
    }

    return ['Candidate profile includes positive ranking signals from ATS analysis.'];
  }

  growthHighlights(): string[] {
    const aiIssues = this.aiIssues();
    if (aiIssues.length > 0) {
      return aiIssues.slice(0, 3);
    }

    const candidate = this.candidate;
    if (!candidate) {
      return [];
    }

    const job = candidate.jobId ? this.dataService.jobs().find((item) => item.id === candidate.jobId) : null;
    if (job) {
      const candidateSkills = new Set(candidate.skills.map((skill) => skill.toLowerCase()));
      const missing = job.requirements.filter((req) => !candidateSkills.has(req.toLowerCase())).slice(0, 3);
      if (missing.length > 0) {
        return missing.map((item) => `Assess depth for requirement: ${item}.`);
      }
    }

    if (candidate.status === 'Screening' || candidate.status === 'Applied') {
      return ['Complete screening and shortlisting to validate role fit in interview stages.'];
    }

    return ['Validate communication clarity and system design depth during the interview round.'];
  }

  aiSummaryText(): string | null {
    const profile = this.aiProfile();
    if (!profile) {
      return null;
    }

    return profile.geminiSummary || profile.llmSummary || profile.summary || null;
  }

  aiReasons(): string[] {
    const profile = this.aiProfile();
    if (!profile) {
      return [];
    }

    return profile.reasons;
  }

  aiSuggestions(): string[] {
    const profile = this.aiProfile();
    if (!profile) {
      return [];
    }

    return profile.suggestions;
  }

  aiIssues(): string[] {
    const profile = this.aiProfile();
    if (!profile) {
      return [];
    }

    return profile.issues;
  }

  primaryEmail(): string {
    const profileEmail = this.readText(this.aiProfile()?.contact?.['email']);
    return profileEmail || this.candidate?.email || '';
  }

  primaryPhone(): string {
    const profilePhone = this.readText(this.aiProfile()?.contact?.['phone']);
    return profilePhone || this.candidate?.phone || '';
  }

  profileSignals(): Array<{label: string; value: string}> {
    const signals = this.aiProfile()?.signals ?? {};
    return Object.entries(signals)
      .filter(([, value]) => value !== null && value !== undefined && value !== '')
      .slice(0, 8)
      .map(([key, value]) => ({
        label: key.replace(/_/g, ' '),
        value: typeof value === 'number' ? value.toFixed(2) : String(value),
      }));
  }

  experienceTimeline(): Array<Record<string, unknown>> {
    return this.aiProfile()?.experienceTimeline ?? [];
  }

  projects(): Array<Record<string, unknown>> {
    return this.aiProfile()?.projects ?? [];
  }

  educationHistory(): Array<Record<string, unknown>> {
    return this.aiProfile()?.educationHistory ?? [];
  }

  experienceTrack(item: Record<string, unknown>): string {
    return [
      this.readText(item['title']),
      this.readText(item['role']),
      this.readText(item['company']),
      this.readText(item['period']),
      this.readText(item['duration']),
      this.readText(item['value']),
    ].filter(Boolean).join('|');
  }

  experienceHeadline(item: Record<string, unknown>): string {
    return this.readText(item['title'])
      || this.readText(item['role'])
      || this.readText(item['company'])
      || this.readText(item['value'])
      || 'Resume experience';
  }

  experienceMeta(item: Record<string, unknown>): string {
    return this.readText(item['company'])
      || this.readText(item['organization'])
      || this.readText(item['duration'])
      || this.readText(item['period'])
      || 'Candidate resume data';
  }

  experienceSummary(item: Record<string, unknown>): string {
    return this.readText(item['summary']) || this.readText(item['description']);
  }

  projectTrack(item: Record<string, unknown>): string {
    return [
      this.readText(item['name']),
      this.readText(item['title']),
      this.readText(item['value']),
    ].filter(Boolean).join('|');
  }

  projectHeadline(item: Record<string, unknown>): string {
    return this.readText(item['name'])
      || this.readText(item['title'])
      || this.readText(item['value'])
      || 'Project';
  }

  projectSummary(item: Record<string, unknown>): string {
    return this.readText(item['summary']) || this.readText(item['description']);
  }

  educationTrack(item: Record<string, unknown>): string {
    return [
      this.readText(item['degree']),
      this.readText(item['institution']),
      this.readText(item['school']),
      this.readText(item['year']),
      this.readText(item['value']),
    ].filter(Boolean).join('|');
  }

  educationHeadline(item: Record<string, unknown>): string {
    return this.readText(item['degree'])
      || this.readText(item['title'])
      || this.readText(item['value'])
      || 'Education';
  }

  educationMeta(item: Record<string, unknown>): string {
    return this.readText(item['institution'])
      || this.readText(item['school'])
      || this.readText(item['university'])
      || this.readText(item['year'])
      || 'Resume education data';
  }

  private readText(value: unknown): string {
    return typeof value === 'string' ? value.trim() : '';
  }
}
