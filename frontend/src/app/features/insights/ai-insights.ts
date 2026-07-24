import {CommonModule} from '@angular/common';
import {FormsModule} from '@angular/forms';
import {Component, computed, inject, OnInit, signal} from '@angular/core';
import {MatIconModule} from '@angular/material/icon';
import {RouterLink} from '@angular/router';

import {DataService, type AssessmentReportSummary} from '../../core/data.service';
import {AssistantService} from '../../core/assistant.service';

interface Insight {
  id: string;
  category: string;
  icon: string;
  iconBg: string;
  iconColor: string;
  title: string;
  body: string;
  action?: {label: string; route: string};
}

@Component({
  selector: 'app-ai-insights',
  standalone: true,
  imports: [CommonModule, MatIconModule, RouterLink, FormsModule],
  template: `
    <div class="space-y-6 animate-in fade-in duration-300">
      <div class="flex flex-col items-start justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <h1 class="flex items-center gap-2 text-2xl font-bold text-gray-900">
            <mat-icon class="text-primary-600">auto_awesome</mat-icon>
            AI Insights
          </h1>
          <p class="mt-1 text-sm text-gray-500">Live manager guidance built from roles, candidates, and assessment outcomes.</p>
        </div>
        <button
          (click)="refreshInsights()"
          [disabled]="isGenerating()"
          class="flex items-center gap-2 rounded-xl bg-primary-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm shadow-primary-500/20 transition-all hover:bg-primary-700 disabled:opacity-50"
        >
          <mat-icon class="text-[18px]" [class.animate-spin]="isGenerating()">{{ isGenerating() ? 'progress_activity' : 'refresh' }}</mat-icon>
          {{ isGenerating() ? 'Generating...' : 'Refresh Insights' }}
        </button>
      </div>

      <div class="grid grid-cols-2 gap-3 lg:grid-cols-5">
        @for (stat of pipelineStats(); track stat.label) {
          <div class="rounded-2xl border border-rose-100 bg-white p-4 text-center shadow-sm">
            <p class="text-2xl font-bold" [class]="stat.colorClass">{{ stat.value }}</p>
            <p class="mt-1 text-xs font-medium text-gray-500">{{ stat.label }}</p>
          </div>
        }
      </div>

      @if (isGenerating()) {
        <div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
          @for (i of [1, 2, 3, 4]; track i) {
            <div class="animate-pulse rounded-2xl border border-rose-100 bg-white p-5 shadow-sm">
              <div class="mb-3 flex gap-3">
                <div class="h-10 w-10 rounded-xl bg-rose-100"></div>
                <div class="flex-1">
                  <div class="mb-2 h-3 w-1/4 rounded bg-rose-100"></div>
                  <div class="h-4 w-2/3 rounded bg-rose-100"></div>
                </div>
              </div>
              <div class="space-y-2">
                <div class="h-3 rounded bg-rose-100"></div>
                <div class="h-3 w-4/5 rounded bg-rose-100"></div>
              </div>
            </div>
          }
        </div>
      } @else if (insights().length > 0) {
        <div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
          @for (insight of insights(); track insight.id) {
            <div class="group rounded-2xl border border-rose-100 bg-white p-5 shadow-sm transition-shadow hover:shadow-md">
              <div class="mb-3 flex items-start gap-3">
                <div [class]="'flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ' + insight.iconBg">
                  <mat-icon [class]="'text-[20px] ' + insight.iconColor">{{ insight.icon }}</mat-icon>
                </div>
                <div class="min-w-0 flex-1">
                  <span class="text-[10px] font-bold uppercase tracking-wider text-gray-400">{{ insight.category }}</span>
                  <h3 class="mt-0.5 text-sm font-semibold text-gray-900">{{ insight.title }}</h3>
                </div>
              </div>
              <p class="text-sm leading-relaxed text-gray-600">{{ insight.body }}</p>
              @if (insight.action) {
                <a
                  [routerLink]="insight.action.route"
                  class="mt-3 inline-flex items-center gap-1 text-xs font-semibold text-primary-600 hover:underline"
                >
                  {{ insight.action.label }} <mat-icon class="text-[14px]">arrow_forward</mat-icon>
                </a>
              }
            </div>
          }
        </div>
      } @else {
        <div class="rounded-2xl border border-rose-100 bg-white p-12 text-center shadow-sm">
          <div class="mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-2xl bg-rose-50">
            <mat-icon class="text-[32px] text-primary-500">auto_awesome</mat-icon>
          </div>
          <h3 class="mb-2 text-lg font-semibold text-gray-900">No insights yet</h3>
          <p class="mx-auto mb-6 max-w-sm text-sm text-gray-500">
            Create a role to generate candidate shortlists and assessment activity that the insight engine can analyze.
          </p>
          <a routerLink="/jobs/create" class="inline-flex items-center gap-2 rounded-xl bg-primary-600 px-5 py-2.5 text-sm font-semibold text-white transition-all hover:bg-primary-700">
            <mat-icon class="text-[18px]">add</mat-icon> Create First Job Role
          </a>
        </div>
      }

      <div class="overflow-hidden rounded-2xl border border-rose-100 bg-white shadow-sm">
        <div class="border-b border-rose-100 p-5">
          <h2 class="font-semibold text-gray-900">Ask a Custom Question</h2>
          <p class="mt-0.5 text-xs text-gray-500">Query your hiring data with natural language</p>
        </div>
        <div class="p-5">
          <div class="flex gap-3">
            <input
              [(ngModel)]="customQuery"
              type="text"
              placeholder="e.g. Which candidates are strongest for active roles?"
              class="flex-1 rounded-xl border border-rose-200 bg-white px-4 py-2.5 text-sm text-gray-900 placeholder-gray-400 transition-all focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-500/20"
            />
            <button
              (click)="askCustomQuery()"
              [disabled]="!customQuery.trim() || customQueryLoading()"
              class="flex shrink-0 items-center gap-2 rounded-xl bg-primary-600 px-4 py-2.5 text-sm font-semibold text-white transition-all hover:bg-primary-700 disabled:opacity-50"
            >
              <mat-icon class="text-[18px]" [class.animate-spin]="customQueryLoading()">{{ customQueryLoading() ? 'progress_activity' : 'send' }}</mat-icon>
            </button>
          </div>
          @if (customAnswer()) {
            <div class="mt-4 whitespace-pre-wrap rounded-xl border border-rose-100 bg-rose-50/60 p-4 text-sm leading-relaxed text-gray-800">
              {{ customAnswer() }}
            </div>
          }
        </div>
      </div>
    </div>
  `,
})
export class AiInsightsComponent implements OnInit {
  private dataService = inject(DataService);
  private assistantService = inject(AssistantService);

  isGenerating = signal(false);
  insights = signal<Insight[]>([]);
  reportSummaries = signal<AssessmentReportSummary[]>([]);
  customQuery = '';
  customQueryLoading = signal(false);
  customAnswer = signal<string | null>(null);

  pipelineStats = computed(() => {
    const candidates = this.dataService.candidates();
    const jobs = this.dataService.jobs();
    const reports = this.reportSummaries();
    const countByStatus = (status: string) => candidates.filter((candidate) => candidate.status === status).length;

    return [
      {label: 'Active Roles', value: jobs.filter((job) => job.status === 'Active').length, colorClass: 'text-primary-600'},
      {label: 'Total Candidates', value: candidates.length, colorClass: 'text-gray-900'},
      {label: 'Shortlisted', value: countByStatus('Shortlisted'), colorClass: 'text-primary-700'},
      {label: 'Reports Ready', value: reports.filter((item) => item.reportAvailable).length, colorClass: 'text-rose-700'},
      {label: 'Hired', value: countByStatus('Hired'), colorClass: 'text-primary-800'},
    ];
  });

  async ngOnInit(): Promise<void> {
    await this.dataService.loadJobs();
    await this.dataService.refreshCandidates();
    await this.generateInsights();
  }

  async refreshInsights(): Promise<void> {
    await this.generateInsights();
  }

  async generateInsights(): Promise<void> {
    this.isGenerating.set(true);
    this.insights.set([]);

    const candidates = this.dataService.candidates();
    const jobs = this.dataService.jobs();
    const reportSummaries = await this.safeLoadReportSummaries();
    this.reportSummaries.set(reportSummaries);

    const generatedInsights: Insight[] = [];
    const activeJobs = jobs.filter((job) => job.status === 'Active');
    const shortlisted = candidates.filter((candidate) => candidate.status === 'Shortlisted').length;
    const interview = candidates.filter((candidate) => candidate.status === 'Interview').length;
    const zeroCandidateJobs = activeJobs.filter((job) => job.candidatesCount === 0);
    const reportReady = reportSummaries.filter((item) => item.reportAvailable).length;
    const terminated = reportSummaries.filter((item) => item.sessionStatus === 'TERMINATED').length;
    const topCandidates = candidates
      .slice()
      .sort((left, right) => right.matchScore - left.matchScore)
      .slice(0, 3);
    const avgScore = candidates.length > 0
      ? Math.round(candidates.reduce((sum, candidate) => sum + candidate.matchScore, 0) / candidates.length)
      : 0;

    if (activeJobs.length > 0) {
      generatedInsights.push({
        id: '1',
        category: 'Pipeline Health',
        icon: 'trending_up',
        iconBg: 'bg-rose-50',
        iconColor: 'text-rose-700',
        title: `${activeJobs.length} active role${activeJobs.length !== 1 ? 's' : ''} in progress`,
        body: `${shortlisted} shortlisted and ${interview} invited candidate${interview !== 1 ? 's are' : ' is'} currently moving through the funnel.`,
        action: {label: 'View roles', route: '/jobs'},
      });
    }

    if (topCandidates.length > 0) {
      generatedInsights.push({
        id: '2',
        category: 'Quality Signal',
        icon: 'star',
        iconBg: 'bg-primary-50',
        iconColor: 'text-primary-700',
        title: `Average match score: ${avgScore}%`,
        body: `Top current profiles: ${topCandidates.map((candidate) => `${candidate.name} (${candidate.matchScore}%)`).join(', ')}.`,
        action: {label: 'Open chat', route: '/chat'},
      });
    }

    if (zeroCandidateJobs.length > 0) {
      generatedInsights.push({
        id: '3',
        category: 'Coverage Gap',
        icon: 'warning_amber',
        iconBg: 'bg-red-50',
        iconColor: 'text-red-700',
        title: `${zeroCandidateJobs.length} role${zeroCandidateJobs.length !== 1 ? 's' : ''} need stronger supply`,
        body: `No matched candidates are currently available for ${zeroCandidateJobs.slice(0, 3).map((job) => job.title).join(', ')}.`,
        action: {label: 'Review roles', route: '/jobs'},
      });
    }

    if (reportReady > 0 || terminated > 0) {
      generatedInsights.push({
        id: '4',
        category: 'Assessment Signal',
        icon: 'assignment_turned_in',
        iconBg: 'bg-rose-50',
        iconColor: 'text-rose-700',
        title: `${reportReady} report${reportReady !== 1 ? 's' : ''} ready${terminated > 0 ? `, ${terminated} terminated` : ''}`,
        body: terminated > 0
          ? 'Some sessions ended early because of integrity or session issues. Review those candidates before progressing them.'
          : 'Fresh assessment outcomes are available and ready for manager review.',
        action: {label: 'Open reports', route: '/reports'},
      });
    }

    generatedInsights.push({
      id: '5',
      category: 'AI Recommendation',
      icon: 'psychology',
      iconBg: 'bg-primary-50',
      iconColor: 'text-primary-700',
      title: 'Use HireAgent for named answers',
      body: 'Ask for top candidates, role-specific gaps, or report-backed recommendations. HireAgent now has richer platform context.',
      action: {label: 'Open chat', route: '/chat'},
    });

    await new Promise((resolve) => setTimeout(resolve, 300));
    this.insights.set(generatedInsights);
    this.isGenerating.set(false);
  }

  async askCustomQuery(): Promise<void> {
    const query = this.customQuery.trim();
    if (!query) {
      return;
    }

    this.customQueryLoading.set(true);
    this.customAnswer.set(null);
    try {
      const answer = await this.assistantService.answer(query);
      this.customAnswer.set(answer);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to get an answer right now. Please try again.';
      this.customAnswer.set(message);
    } finally {
      this.customQueryLoading.set(false);
    }
  }

  private async safeLoadReportSummaries(): Promise<AssessmentReportSummary[]> {
    try {
      return await this.dataService.getAssessmentReportSummaries();
    } catch {
      return [];
    }
  }
}
