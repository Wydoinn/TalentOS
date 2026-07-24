import { Component, inject, OnInit, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { Router, RouterLink, ActivatedRoute } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { DataService, Job, Candidate } from '../../core/data.service';

@Component({
  selector: 'app-job-candidates',
  standalone: true,
  imports: [MatIconModule, RouterLink, FormsModule],
  template: `
    <div class="space-y-6 animate-in">
      <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div class="flex items-center gap-4">
          <a routerLink="/jobs" class="rounded-full p-2 transition-colors hover:bg-rose-50">
            <mat-icon>arrow_back</mat-icon>
          </a>
          <div>
            <h1 class="text-2xl font-bold text-gray-900">Candidates for {{ job()?.title || 'Role' }}</h1>
            <p class="text-sm text-gray-500">Matched using ATS Parser and Checker</p>
          </div>
        </div>

      </div>

      @if (dataService.errorMessage()) {
        <div class="text-sm text-red-600 bg-red-50 border border-red-100 rounded-xl px-4 py-3">
          {{ dataService.errorMessage() }}
        </div>
      }

      @if (matchingStatus()) {
        <div class="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          {{ matchingStatus() }}
        </div>
      }

      @if (job()) {
        <div class="rounded-2xl border border-rose-100 bg-white p-5 shadow-sm">
          <div class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <p class="text-xs font-semibold uppercase tracking-[0.18em] text-primary-600">Ranking Controls</p>
              <h2 class="mt-2 text-lg font-semibold text-slate-900">Tune candidate retrieval for this role</h2>
              <p class="mt-1 text-sm text-slate-500">Source pools, ATS threshold, retrieval depth, and final shortlist count all map to backend ranking controls.</p>
            </div>
          </div>

          <div class="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            <div>
              <label class="mb-1.5 block text-sm font-medium text-slate-700">Source</label>
              <select [(ngModel)]="rankingOptions.source" name="source" class="w-full rounded-xl border border-rose-200 bg-white px-4 py-2.5 text-sm text-slate-700 outline-none focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20">
                <option value="all">All resume pools</option>
                <option value="internal">Internal ATS only</option>
                <option value="external">External ATS only</option>
              </select>
            </div>

            <div>
              <label class="mb-1.5 block text-sm font-medium text-slate-700">Minimum ATS Score</label>
              <input [(ngModel)]="rankingOptions.minimumAtsScore" name="minimumAtsScore" type="number" min="0" max="100" class="w-full rounded-xl border border-rose-200 bg-white px-4 py-2.5 text-sm text-slate-700 outline-none focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20" />
            </div>

            <div>
              <label class="mb-1.5 block text-sm font-medium text-slate-700">Top N</label>
              <input [(ngModel)]="rankingOptions.topN" name="topN" type="number" min="1" max="100" class="w-full rounded-xl border border-rose-200 bg-white px-4 py-2.5 text-sm text-slate-700 outline-none focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20" />
            </div>

            <div>
              <label class="mb-1.5 block text-sm font-medium text-slate-700">Retrieval Top K</label>
              <input [(ngModel)]="rankingOptions.retrievalTopK" name="retrievalTopK" type="number" min="1" max="200" class="w-full rounded-xl border border-rose-200 bg-white px-4 py-2.5 text-sm text-slate-700 outline-none focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20" />
            </div>

            <div>
              <label class="mb-1.5 block text-sm font-medium text-slate-700">Candidate Pool Size</label>
              <input [(ngModel)]="rankingOptions.candidatePoolSize" name="candidatePoolSize" type="number" min="1" max="500" class="w-full rounded-xl border border-rose-200 bg-white px-4 py-2.5 text-sm text-slate-700 outline-none focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20" />
            </div>

            <div>
              <label class="mb-1.5 block text-sm font-medium text-slate-700">Final Top K</label>
              <input [(ngModel)]="rankingOptions.finalTopK" name="finalTopK" type="number" min="1" max="100" class="w-full rounded-xl border border-rose-200 bg-white px-4 py-2.5 text-sm text-slate-700 outline-none focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20" />
            </div>
          </div>
        </div>
      }

      <div class="flex flex-col overflow-hidden rounded-2xl border border-rose-100 bg-white shadow-sm">
        <div class="overflow-x-auto p-0">
          <table class="w-full min-w-[720px] border-collapse text-left">
            <thead>
              <tr class="bg-rose-50/70 text-xs uppercase tracking-wider text-rose-700">
                <th class="px-6 py-4 font-medium">Candidate</th>
                <th class="px-6 py-4 font-medium">AI Match Score</th>
                <th class="px-6 py-4 font-medium">Source</th>
                <th class="px-6 py-4 font-medium">Status</th>
                <th class="px-6 py-4 font-medium text-right">Action</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-rose-100 text-sm">
              @if (candidates().length === 0) {
                <tr>
                  <td colspan="5" class="px-6 py-10 text-center text-sm text-gray-500">
                    @if (ranking()) {
                      Matching candidates using ATS Parser and Checker...
                    } @else {
                      No matched candidates yet for this role.
                    }
                  </td>
                </tr>
              } @else {
                @for (candidate of candidates(); track candidate.id) {
                  <tr class="transition-colors hover:bg-rose-50/60">
                    <td class="px-6 py-4">
                      <div class="flex items-center gap-3">
                        <img [src]="candidate.avatar" alt="Avatar" class="h-10 w-10 rounded-full bg-rose-50" />
                        <div>
                          <p class="font-medium text-gray-900">{{ candidate.name }}</p>
                          <p class="text-xs text-gray-500">{{ candidate.role }}</p>
                        </div>
                      </div>
                    </td>
                    <td class="px-6 py-4">
                      <div class="flex items-center gap-3">
                        <div class="h-2 w-full max-w-[100px] rounded-full bg-rose-100">
                          <div class="h-2 rounded-full bg-primary-600" [style.width.%]="candidate.matchScore"></div>
                        </div>
                        <span class="text-sm font-semibold text-rose-700">{{ candidate.matchScore }}%</span>
                      </div>
                    </td>
                    <td class="px-6 py-4">
                      @if (candidate.source) {
                        <span class="inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.12em]"
                          [class]="candidate.source === 'internal' ? 'bg-primary-50 text-primary-700' : 'bg-rose-50 text-rose-700'">
                          {{ candidate.source }}
                        </span>
                      } @else {
                        <span class="text-xs text-gray-500">Unknown</span>
                      }
                    </td>
                    <td class="px-6 py-4">
                      <span class="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium"
                            [class.bg-rose-100]="candidate.status === 'Interview'"
                            [class.text-rose-700]="candidate.status === 'Interview'"
                            [class.bg-slate-100]="candidate.status === 'Applied'"
                            [class.text-slate-600]="candidate.status === 'Applied'"
                            [class.bg-primary-50]="candidate.status === 'Shortlisted'"
                            [class.text-primary-700]="candidate.status === 'Shortlisted'"
                            [class.bg-red-50]="candidate.status === 'Rejected'"
                            [class.text-red-600]="candidate.status === 'Rejected'">
                        {{ candidate.status }}
                      </span>
                    </td>
                    <td class="px-6 py-4 text-right">
                      <a
                        [routerLink]="['/candidates', encodeCandidateId(candidate.id)]"
                        [queryParams]="candidateProfileQuery(candidate)"
                        class="rounded-lg px-3 py-1.5 font-medium text-primary-700 transition-colors hover:bg-rose-50"
                      >
                        View Profile
                      </a>
                    </td>
                  </tr>
                }
              }
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `
})
export class JobCandidatesComponent implements OnInit {
  dataService = inject(DataService);
  route = inject(ActivatedRoute);
  router = inject(Router);

  job = signal<Job | null>(null);
  candidates = signal<Candidate[]>([]);
  ranking = signal(false);
  matchingStatus = signal<string | null>(null);
  rankingOptions = {
    source: 'all' as 'all' | 'internal' | 'external',
    minimumAtsScore: null as number | null,
    topN: 5,
    retrievalTopK: null as number | null,
    candidatePoolSize: null as number | null,
    finalTopK: null as number | null,
  };

  ngOnInit() {
    void this.initialize();
  }

  private async initialize(): Promise<void> {
    await this.dataService.loadJobs();

    const id = this.route.snapshot.paramMap.get('id');
    if (id) {
      this.job.set(this.dataService.jobs().find(j => j.id === id) || null);
      if (this.job()) {
        this.candidates.set(await this.dataService.loadJobCandidates(this.job()!.id));

        const autoRun = this.route.snapshot.queryParamMap.get('autorun') === '1';
        if (autoRun) {
          this.matchingStatus.set('Matching candidates using ATS Parser and Checker...');
          try {
            await this.runRanking();
            this.matchingStatus.set(`Candidate matching completed. ${this.candidates().length} candidate(s) found.`);
          } catch {
            this.matchingStatus.set(null);
          } finally {
            void this.router.navigate([], {
              relativeTo: this.route,
              queryParams: {autorun: null},
              queryParamsHandling: 'merge',
              replaceUrl: true,
            });
          }
        }
      }
    }
  }

  async runRanking(): Promise<void> {
    const job = this.job();
    if (!job) {
      return;
    }

    try {
      this.ranking.set(true);
      this.matchingStatus.set('Matching candidates using ATS Parser and Checker...');
      await this.dataService.rankCandidates(job.id, {
        source: this.rankingOptions.source,
        minimumAtsScore: this.normalizeOptionalNumber(this.rankingOptions.minimumAtsScore),
        topN: this.normalizeOptionalNumber(this.rankingOptions.topN),
        retrievalTopK: this.normalizeOptionalNumber(this.rankingOptions.retrievalTopK),
        candidatePoolSize: this.normalizeOptionalNumber(this.rankingOptions.candidatePoolSize),
        finalTopK: this.normalizeOptionalNumber(this.rankingOptions.finalTopK),
      });
      this.candidates.set(await this.dataService.loadJobCandidates(job.id));
      this.matchingStatus.set(`Candidate matching completed. ${this.candidates().length} candidate(s) found.`);
    } catch {
      this.matchingStatus.set(null);
    } finally {
      this.ranking.set(false);
    }
  }

  encodeCandidateId(candidateId: string): string {
    return encodeURIComponent(candidateId);
  }

  candidateProfileQuery(candidate: Candidate): Record<string, string> {
    const query: Record<string, string> = {};

    if (candidate.jobId) {
      query['jobId'] = candidate.jobId;
    }
    if (candidate.matchId) {
      query['matchId'] = candidate.matchId;
    }

    return query;
  }

  private normalizeOptionalNumber(value: number | null): number | null {
    return typeof value === 'number' && Number.isFinite(value) && value > 0
      ? Math.trunc(value)
      : null;
  }
}
