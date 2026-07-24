import {CommonModule} from '@angular/common';
import {Component, computed, inject, OnInit, signal} from '@angular/core';
import {FormsModule} from '@angular/forms';
import {ActivatedRoute, Router} from '@angular/router';
import {MatIconModule} from '@angular/material/icon';

import {DataService, type AssessmentQuestionResult, type AssessmentReportSummary, type AssessmentResult} from '../../core/data.service';

@Component({
  selector: 'app-assessment-reports',
  standalone: true,
  imports: [CommonModule, FormsModule, MatIconModule],
  template: `
    <div class="page-shell animate-in">
      <section class="page-hero p-6">
        <div class="relative flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <span class="brand-chip">Assessment Reports</span>
            <h1 class="mt-4 font-['Space_Grotesk'] text-3xl font-bold">Review candidate outcomes, integrity signals, and answer quality.</h1>
            <p class="mt-3 max-w-2xl text-sm leading-7 text-white/82">
              Every completed or terminated L0 session is collected here with status, scores, and question-by-question answers.
            </p>
          </div>
          <button
            type="button"
            (click)="refresh()"
            [disabled]="loading()"
            class="inline-flex items-center gap-2 rounded-2xl border border-white/20 bg-white/12 px-5 py-3 text-sm font-semibold text-white backdrop-blur hover:bg-white/18 disabled:opacity-50"
          >
            <mat-icon class="text-[18px]" [class.animate-spin]="loading()">{{ loading() ? 'progress_activity' : 'refresh' }}</mat-icon>
            {{ loading() ? 'Loading...' : 'Refresh Reports' }}
          </button>
        </div>
      </section>

      <section class="surface-card p-5">
        <div class="grid gap-3 md:grid-cols-[1fr_12rem]">
          <div class="relative">
            <mat-icon class="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-[20px]">search</mat-icon>
            <input
              [(ngModel)]="searchQuery"
              type="text"
              placeholder="Search candidate or role"
              class="w-full rounded-2xl border border-[var(--brand-line)] bg-white py-3 pl-10 pr-4 text-sm text-[var(--brand-ink)] outline-none focus:border-primary-500 focus:ring-2 focus:ring-primary-500/15"
            />
          </div>
          <select
            [(ngModel)]="statusFilter"
            class="rounded-2xl border border-[var(--brand-line)] bg-white px-4 py-3 text-sm text-[var(--brand-ink)] outline-none focus:border-primary-500 focus:ring-2 focus:ring-primary-500/15"
          >
            <option value="all">All statuses</option>
            <option value="report_ready">Report ready</option>
            <option value="in_progress">In progress</option>
            <option value="terminated">Terminated</option>
          </select>
        </div>

        <div class="mt-5 space-y-3">
          @if (filteredItems().length === 0 && !loading()) {
            <div class="rounded-2xl border border-dashed border-[var(--brand-line)] bg-[rgba(121,47,140,0.03)] px-4 py-8 text-center text-sm text-[var(--brand-copy-soft)]">
              No assessment sessions matched your filters.
            </div>
          }

          @for (item of filteredItems(); track item.assessmentSessionId) {
            <button
              type="button"
              (click)="selectSummary(item)"
              class="w-full rounded-2xl border border-[var(--brand-line)] bg-white px-4 py-4 text-left transition-colors hover:border-primary-300 hover:bg-primary-50/40"
            >
              <div class="flex items-start justify-between gap-3">
                <div>
                  <p class="text-sm font-semibold text-[var(--brand-ink)]">{{ item.candidateName }}</p>
                  <p class="mt-1 text-xs text-[var(--brand-copy-soft)]">{{ item.jobTitle }}</p>
                </div>
                <span class="rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.14em]" [class]="statusPillClass(item)">
                  {{ item.reportAvailable ? (item.decision || 'Ready') : humanizeStatus(item.sessionStatus) }}
                </span>
              </div>
              <div class="mt-3 flex flex-wrap items-center gap-3 text-xs text-[var(--brand-copy-soft)]">
                <span>Session: {{ humanizeStatus(item.sessionStatus) }}</span>
                @if (showScore(item)) {
                  <span>Score: {{ item.overallScore | number:'1.0-0' }}</span>
                }
                <span>{{ formatDate(item.createdAt) }}</span>
              </div>
            </button>
          }
        </div>
      </section>
    </div>

    @if (selectedSummary()) {
      <div class="fixed inset-0 z-40 flex items-center justify-center bg-[rgba(15,23,42,0.45)] p-4 backdrop-blur-sm" (click)="closeReport()">
        <section class="flex h-[70vh] w-[min(70vw,1100px)] min-w-[320px] flex-col overflow-hidden rounded-[2rem] border border-[var(--brand-line)] bg-white shadow-[0_40px_120px_rgba(15,23,42,0.24)]" (click)="$event.stopPropagation()">
          <header class="flex items-start justify-between gap-4 border-b border-[var(--brand-line)] bg-[rgba(121,47,140,0.03)] px-6 py-5">
            <div>
              <p class="eyebrow">Assessment Report</p>
              <h2 class="mt-2 text-2xl font-semibold text-[var(--brand-ink)]">{{ selectedSummary()!.candidateName }}</h2>
              <p class="mt-1 text-sm text-[var(--brand-copy-soft)]">{{ selectedSummary()!.candidateEmail }} | {{ selectedSummary()!.jobTitle }}</p>
            </div>
            <div class="flex items-center gap-3">
              <span class="rounded-full border border-[var(--brand-line)] bg-white px-4 py-2 text-xs font-semibold text-[var(--brand-ink)]">
                {{ humanizeStatus(selectedSummary()!.sessionStatus) }}
              </span>
              <button type="button" (click)="closeReport()" class="inline-flex h-10 w-10 items-center justify-center rounded-full border border-[var(--brand-line)] bg-white text-[var(--brand-ink)] transition-colors hover:bg-[rgba(121,47,140,0.04)]">
                <mat-icon class="text-[20px]">close</mat-icon>
              </button>
            </div>
          </header>

          <div class="flex-1 overflow-y-auto px-6 py-5">
            @if (loadingReport()) {
              <div class="rounded-2xl border border-[var(--brand-line)] bg-[rgba(121,47,140,0.03)] px-4 py-8 text-center text-sm text-[var(--brand-copy-soft)]">
                Loading assessment report...
              </div>
            } @else if (reportError()) {
              <div class="rounded-2xl border border-[rgba(180,35,24,0.18)] bg-[#fff5f5] px-4 py-4 text-sm text-[#b42318]">
                {{ reportError() }}
              </div>
            } @else if (selectedReport()) {
              <div class="space-y-5">
                <div class="grid gap-4 md:grid-cols-3">
                  @if (showSelectedReportScore()) {
                    <div class="metric-card p-4">
                      <p class="text-xs uppercase tracking-[0.16em] text-[var(--brand-copy-soft)]">Overall</p>
                      <p class="metric-value mt-2 text-3xl">{{ selectedReport()!.overallScore | number:'1.0-0' }}</p>
                    </div>
                  }
                  <div class="metric-card p-4">
                    <p class="text-xs uppercase tracking-[0.16em] text-[var(--brand-copy-soft)]">Decision</p>
                    <p class="mt-3 text-lg font-semibold text-[var(--brand-ink)]">{{ selectedReport()!.decision }}</p>
                  </div>
                  <div class="metric-card p-4">
                    <p class="text-xs uppercase tracking-[0.16em] text-[var(--brand-copy-soft)]">Integrity</p>
                    <p class="mt-3 text-lg font-semibold text-[var(--brand-ink)]">{{ selectedSummary()!.integrityScore ?? selectedReport()!.sectionScores['integrity'] ?? 'N/A' }}</p>
                  </div>
                </div>

                <div class="rounded-2xl border border-[var(--brand-line)] bg-white p-4">
                  <p class="text-sm font-semibold text-[var(--brand-ink)]">Assessment Summary</p>
                  <p class="mt-2 text-sm leading-7 text-[var(--brand-copy-soft)]">{{ selectedReport()!.summary }}</p>
                </div>

                <div class="rounded-2xl border border-[var(--brand-line)] bg-white p-4">
                  <p class="text-sm font-semibold text-[var(--brand-ink)]">Section Scores</p>
                  <div class="mt-4 grid gap-3 md:grid-cols-2">
                    @for (entry of sectionScoreEntries(); track entry.key) {
                      <div class="rounded-xl border border-[var(--brand-line)] bg-[rgba(121,47,140,0.03)] px-4 py-3">
                        <p class="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--brand-copy-soft)]">{{ humanizeStatus(entry.key) }}</p>
                        <p class="mt-2 text-base font-semibold text-[var(--brand-ink)]">{{ entry.value | number:'1.0-1' }}</p>
                      </div>
                    } @empty {
                      <div class="rounded-xl border border-dashed border-[var(--brand-line)] bg-[rgba(121,47,140,0.03)] px-4 py-6 text-sm text-[var(--brand-copy-soft)]">
                        Section-level scores were not available for this report.
                      </div>
                    }
                  </div>
                </div>

                <div class="rounded-2xl border border-[var(--brand-line)] bg-white p-4">
                  <p class="text-sm font-semibold text-[var(--brand-ink)]">Proctoring Summary</p>
                  <p class="mt-2 text-sm leading-7 text-[var(--brand-copy-soft)]">{{ selectedReport()!.proctorSummary || 'No proctoring issues recorded.' }}</p>
                </div>

                <div class="rounded-2xl border border-[var(--brand-line)] bg-white p-4">
                  <p class="text-sm font-semibold text-[var(--brand-ink)]">Proctoring Timeline</p>
                  <div class="mt-4 space-y-3">
                    @for (event of selectedReport()!.flaggedEventsTimeline; track flaggedEventTrack(event, $index)) {
                      <div class="rounded-xl border border-[var(--brand-line)] bg-[rgba(121,47,140,0.03)] px-4 py-3">
                        <div class="flex flex-wrap items-center justify-between gap-2">
                          <p class="text-sm font-semibold text-[var(--brand-ink)]">{{ formatEventLabel(event['event_type']) }}</p>
                          <span class="rounded-full bg-white px-2.5 py-1 text-[11px] font-semibold text-[var(--brand-ink)]">{{ formatEventSeverity(event) }}</span>
                        </div>
                        <p class="mt-2 text-xs text-[var(--brand-copy-soft)]">{{ formatEventTimestamp(event) }}</p>
                      </div>
                    } @empty {
                      <div class="rounded-xl border border-dashed border-[var(--brand-line)] bg-[rgba(121,47,140,0.03)] px-4 py-6 text-sm text-[var(--brand-copy-soft)]">
                        No proctoring events were recorded for this session.
                      </div>
                    }
                  </div>
                </div>

                @if (selectedReport()!.terminationReason) {
                  <div class="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                    {{ selectedReport()!.terminationReason }}
                  </div>
                }

                <div class="rounded-2xl border border-[var(--brand-line)] bg-white p-4">
                  <p class="text-sm font-semibold text-[var(--brand-ink)]">Question and Answer Log</p>
                  <div class="mt-4 space-y-4">
                    @for (item of selectedReport()!.questionResults; track questionTrack(item, $index)) {
                      <div class="rounded-2xl border border-[var(--brand-line)] bg-[rgba(121,47,140,0.03)] p-4">
                        <div class="flex flex-wrap items-center justify-between gap-2">
                          <p class="text-sm font-semibold text-[var(--brand-ink)]">{{ item.prompt || 'Assessment question' }}</p>
                          @if (item.score !== null && item.score !== undefined) {
                            <span class="rounded-full bg-white px-2.5 py-1 text-[11px] font-semibold text-[var(--brand-ink)]">
                              Score {{ item.score | number:'1.0-0' }}
                            </span>
                          }
                        </div>
                        @if (item.classification || item.confidence !== null && item.confidence !== undefined) {
                          <p class="mt-2 text-xs text-[var(--brand-copy-soft)]">
                            {{ item.classification || 'Needs Review' }}
                            @if (item.confidence !== null && item.confidence !== undefined) {
                              | Confidence {{ item.confidence | number:'1.0-2' }}
                            }
                          </p>
                        }
                        <div class="mt-3 grid gap-3 lg:grid-cols-[1.2fr_0.8fr]">
                          <div class="rounded-xl border border-[var(--brand-line)] bg-white p-3">
                            <p class="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--brand-copy-soft)]">Candidate Response</p>
                            <p class="mt-2 whitespace-pre-wrap text-sm leading-6 text-[var(--brand-ink)]">{{ displayAnswer(item) }}</p>
                          </div>
                          <div class="rounded-xl border border-[var(--brand-line)] bg-white p-3">
                            <p class="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--brand-copy-soft)]">Evaluation Notes</p>
                            @if ((item.reasons?.length ?? 0) > 0) {
                              <div class="mt-2 space-y-1">
                                @for (reason of item.reasons ?? []; track reason) {
                                  <p class="text-sm leading-6 text-[var(--brand-ink)]">{{ reason }}</p>
                                }
                              </div>
                            } @else {
                              <p class="mt-2 text-sm leading-6 text-[var(--brand-copy-soft)]">No evaluation notes recorded.</p>
                            }
                          </div>
                        </div>
                      </div>
                    } @empty {
                      <div class="rounded-2xl border border-dashed border-[var(--brand-line)] bg-[rgba(121,47,140,0.03)] px-4 py-8 text-center text-sm text-[var(--brand-copy-soft)]">
                        No per-question answers were recorded for this session.
                      </div>
                    }
                  </div>
                </div>
              </div>
            } @else {
              <div class="rounded-2xl border border-[var(--brand-line)] bg-[rgba(121,47,140,0.03)] px-4 py-8 text-center text-sm text-[var(--brand-copy-soft)]">
                {{ selectedSummary()!.terminationReason || 'This session exists, but its final assessment report is not available yet.' }}
              </div>
            }
          </div>
        </section>
      </div>
    }
  `,
})
export class AssessmentReportsComponent implements OnInit {
  private dataService = inject(DataService);
  private route = inject(ActivatedRoute);
  private router = inject(Router);

  loading = signal(false);
  loadingReport = signal(false);
  reportError = signal<string | null>(null);
  items = signal<AssessmentReportSummary[]>([]);
  selectedSummary = signal<AssessmentReportSummary | null>(null);
  selectedReport = signal<AssessmentResult | null>(null);

  searchQuery = '';
  statusFilter = 'all';

  filteredItems = computed(() => {
    const query = this.searchQuery.trim().toLowerCase();

    return this.items().filter((item) => {
      const queryMatch = !query
        || item.candidateName.toLowerCase().includes(query)
        || item.candidateEmail.toLowerCase().includes(query)
        || item.jobTitle.toLowerCase().includes(query);

      const statusMatch = this.statusFilter === 'all'
        || (this.statusFilter === 'report_ready' && item.reportAvailable)
        || (this.statusFilter === 'in_progress' && !item.reportAvailable && item.sessionStatus !== 'TERMINATED')
        || (this.statusFilter === 'terminated' && item.sessionStatus === 'TERMINATED');

      return queryMatch && statusMatch;
    });
  });

  async ngOnInit(): Promise<void> {
    await this.refresh();

    this.route.queryParamMap.subscribe((params) => {
      const sessionId = params.get('sessionId');
      if (!sessionId?.trim()) {
        return;
      }

      const match = this.items().find((item) => item.assessmentSessionId === sessionId.trim());
      if (match) {
        void this.selectSummary(match);
      }
    });
  }

  async refresh(): Promise<void> {
    try {
      this.reportError.set(null);
      this.loading.set(true);
      this.items.set(await this.dataService.getAssessmentReportSummaries());
    } catch {
      this.reportError.set(this.dataService.errorMessage() ?? 'Unable to load assessment reports.');
    } finally {
      this.loading.set(false);
    }
  }

  async selectSummary(item: AssessmentReportSummary): Promise<void> {
    this.selectedSummary.set(item);
    this.reportError.set(null);

    await this.router.navigate([], {
      relativeTo: this.route,
      queryParams: {sessionId: item.assessmentSessionId},
      queryParamsHandling: 'merge',
      replaceUrl: true,
    });

    if (!item.reportAvailable) {
      this.selectedReport.set(null);
      return;
    }

    try {
      this.loadingReport.set(true);
      this.selectedReport.set(await this.dataService.getAssessmentReport(item.assessmentSessionId));
    } catch {
      this.selectedReport.set(null);
      this.reportError.set(this.dataService.errorMessage() ?? 'Unable to load assessment report.');
    } finally {
      this.loadingReport.set(false);
    }
  }

  async closeReport(): Promise<void> {
    this.selectedSummary.set(null);
    this.selectedReport.set(null);
    this.reportError.set(null);

    await this.router.navigate([], {
      relativeTo: this.route,
      queryParams: {sessionId: null},
      queryParamsHandling: 'merge',
      replaceUrl: true,
    });
  }

  humanizeStatus(value: string): string {
    return value.replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase());
  }

  formatDate(value: string): string {
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
      return value;
    }

    return parsed.toLocaleString('default', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  }

  statusPillClass(item: AssessmentReportSummary): string {
    if (item.sessionStatus === 'TERMINATED') {
      return 'bg-red-50 text-red-700';
    }
    if (item.reportAvailable) {
      return 'bg-primary-50 text-primary-700';
    }
    return 'bg-[rgba(52,50,91,0.08)] text-[var(--brand-ink)]';
  }

  showScore(item: AssessmentReportSummary): boolean {
    return item.overallScore !== null && item.sessionStatus !== 'TERMINATED';
  }

  showSelectedReportScore(): boolean {
    return !this.selectedReport()?.terminationReason;
  }

  displayAnswer(item: AssessmentQuestionResult): string {
    return item.answerText || item.answerTranscript || 'No answer captured.';
  }

  questionTrack(item: AssessmentQuestionResult, index: number): string {
    return `${index}:${String(item.questionId ?? item.prompt ?? '')}`;
  }

  sectionScoreEntries(): Array<{key: string; value: number}> {
    const sectionScores = this.selectedReport()?.sectionScores ?? {};
    return Object.entries(sectionScores)
      .map(([key, value]) => ({
        key,
        value: typeof value === 'number' ? value : Number(value),
      }))
      .filter((entry) => Number.isFinite(entry.value));
  }

  flaggedEventTrack(event: Record<string, unknown>, index: number): string {
    return `${index}:${String(event['event_type'] ?? event['timestamp'] ?? '')}`;
  }

  formatEventLabel(value: unknown): string {
    return this.humanizeStatus(String(value ?? 'proctor_event'));
  }

  formatEventSeverity(event: Record<string, unknown>): string {
    return this.humanizeStatus(String(event['severity'] ?? 'INFO'));
  }

  formatEventTimestamp(event: Record<string, unknown>): string {
    return this.formatDate(String(event['timestamp'] ?? this.selectedSummary()?.createdAt ?? ''));
  }
}
