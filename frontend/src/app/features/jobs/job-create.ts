import { Component, inject, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink, Router } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { DataService } from '../../core/data.service';

@Component({
  selector: 'app-job-create',
  standalone: true,
  imports: [MatIconModule, RouterLink, FormsModule],
  template: `
    <div class="mx-auto max-w-3xl space-y-6 animate-in">
      <div class="flex items-center gap-4">
        <a routerLink="/jobs" class="rounded-full p-2 transition-colors hover:bg-rose-50">
          <mat-icon>arrow_back</mat-icon>
        </a>
        <div>
          <h1 class="text-2xl font-bold text-slate-900">Create New Role</h1>
          <p class="text-sm text-slate-500">Define role details and configure candidate assessment booking.</p>
        </div>
      </div>

      <div class="rounded-2xl border border-rose-100 bg-white p-6 shadow-sm">
        <form class="space-y-6" (ngSubmit)="onSubmit()">
          <div>
            <label for="title" class="mb-1.5 block text-sm font-medium text-slate-700">Job Title</label>
            <input id="title" type="text" name="title" [(ngModel)]="job.title" required class="w-full rounded-xl border border-rose-200 bg-white px-4 py-2.5 outline-none transition-all focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20" placeholder="e.g. Senior Frontend Developer" />
          </div>

          <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label for="department" class="mb-1.5 block text-sm font-medium text-slate-700">Department</label>
              <input id="department" type="text" name="department" [(ngModel)]="job.department" required class="w-full rounded-xl border border-rose-200 bg-white px-4 py-2.5 outline-none transition-all focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20" placeholder="e.g. Engineering" />
            </div>
            <div>
              <label for="location" class="mb-1.5 block text-sm font-medium text-slate-700">Location</label>
              <input id="location" type="text" name="location" [(ngModel)]="job.location" required class="w-full rounded-xl border border-rose-200 bg-white px-4 py-2.5 outline-none transition-all focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20" placeholder="e.g. Remote" />
            </div>
          </div>

          <div>
            <label for="description" class="mb-1.5 block text-sm font-medium text-slate-700">Job Description</label>
            <textarea id="description" rows="5" name="description" [(ngModel)]="job.description" required class="w-full resize-none rounded-xl border border-rose-200 bg-white px-4 py-2.5 outline-none transition-all focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20" placeholder="Describe the role..."></textarea>
          </div>

          <div>
            <label for="requirements" class="mb-1.5 block text-sm font-medium text-slate-700">Requirements (comma separated)</label>
            <input id="requirements" type="text" name="requirements" [(ngModel)]="requirementsStr" required class="w-full rounded-xl border border-rose-200 bg-white px-4 py-2.5 outline-none transition-all focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20" placeholder="e.g. React, TypeScript, 5+ Years Exp" />
          </div>

          <div class="space-y-4 rounded-xl border border-rose-100 bg-rose-50/50 p-4">
            <h3 class="text-sm font-semibold text-slate-900">Assessment Booking Window</h3>
            <div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
              <div>
                <label for="assessmentStartDate" class="mb-1.5 block text-sm font-medium text-slate-700">Start Date</label>
                <input id="assessmentStartDate" type="date" name="assessmentStartDate" [(ngModel)]="assessmentStartDate" required class="w-full rounded-xl border border-rose-200 bg-white px-4 py-2.5 outline-none transition-all focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20" />
              </div>
              <div>
                <label for="assessmentStartTime" class="mb-1.5 block text-sm font-medium text-slate-700">Start Time</label>
                <input id="assessmentStartTime" type="time" step="300" name="assessmentStartTime" [(ngModel)]="assessmentStartTime" required class="w-full rounded-xl border border-rose-200 bg-white px-4 py-2.5 outline-none transition-all focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20" />
              </div>
              <div>
                <label for="assessmentEndDate" class="mb-1.5 block text-sm font-medium text-slate-700">End Date</label>
                <input id="assessmentEndDate" type="date" name="assessmentEndDate" [(ngModel)]="assessmentEndDate" required class="w-full rounded-xl border border-rose-200 bg-white px-4 py-2.5 outline-none transition-all focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20" />
              </div>
              <div>
                <label for="assessmentEndTime" class="mb-1.5 block text-sm font-medium text-slate-700">End Time</label>
                <input id="assessmentEndTime" type="time" step="300" name="assessmentEndTime" [(ngModel)]="assessmentEndTime" required class="w-full rounded-xl border border-rose-200 bg-white px-4 py-2.5 outline-none transition-all focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20" />
              </div>
            </div>

            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label for="assessmentTimezone" class="mb-1.5 block text-sm font-medium text-slate-700">Timezone</label>
                <input id="assessmentTimezone" type="text" name="assessmentTimezone" [(ngModel)]="job.assessmentTimezone" class="w-full rounded-xl border border-rose-200 bg-white px-4 py-2.5 outline-none transition-all focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20" placeholder="UTC" />
              </div>
              <div>
                <label for="assessmentSlotMinutes" class="mb-1.5 block text-sm font-medium text-slate-700">Slot Duration (minutes)</label>
                <input id="assessmentSlotMinutes" type="number" min="5" max="180" name="assessmentSlotMinutes" [(ngModel)]="job.assessmentSlotMinutes" class="w-full rounded-xl border border-rose-200 bg-white px-4 py-2.5 outline-none transition-all focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20" />
              </div>
            </div>
          </div>

          <div class="space-y-4 rounded-xl border border-rose-100 bg-white p-4">
            <div>
              <h3 class="text-sm font-semibold text-slate-900">Question Blueprint</h3>
              <p class="mt-1 text-xs text-slate-500">These counts drive the Gemini-powered L0 assessment structure for this role.</p>
            </div>

            <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
              @for (item of questionBlueprint; track item.stage) {
                <div>
                  <label class="mb-1.5 block text-sm font-medium text-slate-700">{{ item.stage.replace('_', ' ') }}</label>
                  <input
                    type="number"
                    min="1"
                    max="20"
                    [name]="'questionBlueprint-' + item.stage"
                    [(ngModel)]="item.count"
                    class="w-full rounded-xl border border-rose-200 bg-white px-4 py-2.5 outline-none transition-all focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20"
                  />
                </div>
              }
            </div>
          </div>

          @if (submitError()) {
            <p class="text-sm text-red-600 bg-red-50 border border-red-100 rounded-lg px-3 py-2">
              {{ submitError() }}
            </p>
          }

          <div class="flex justify-end gap-3 border-t border-rose-100 pt-4">
            <button type="button" routerLink="/jobs" class="rounded-xl px-4 py-2 font-medium text-slate-700 transition-colors hover:bg-rose-50">Cancel</button>
            <button type="submit" [disabled]="saving()" class="rounded-xl bg-primary-600 px-4 py-2 font-medium text-white shadow-sm shadow-primary-500/30 transition-colors hover:bg-primary-700 disabled:cursor-not-allowed disabled:opacity-50">
              {{ saving() ? 'Creating...' : 'Create Role' }}
            </button>
          </div>
        </form>
      </div>
    </div>
  `
})
export class JobCreateComponent {
  dataService = inject(DataService);
  router = inject(Router);
  saving = signal(false);
  submitError = signal<string | null>(null);

  job = {
    title: '',
    department: '',
    location: '',
    description: '',
    assessmentTimezone: 'UTC',
    assessmentSlotMinutes: 30,
  };
  assessmentStartDate = '';
  assessmentStartTime = '';
  assessmentEndDate = '';
  assessmentEndTime = '';
  requirementsStr = '';
  questionBlueprint = [
    {stage: 'INTRO', count: 1},
    {stage: 'CANDIDATE_INFO', count: 1},
    {stage: 'ROLE_SPECIFIC', count: 10},
    {stage: 'CODING', count: 2},
    {stage: 'SUMMARY', count: 1},
  ];

  async onSubmit() {
    this.submitError.set(null);

    const assessmentStartAt = this.composeDateTime(this.assessmentStartDate, this.assessmentStartTime);
    const assessmentEndAt = this.composeDateTime(this.assessmentEndDate, this.assessmentEndTime);

    if (!this.job.title || !this.job.department || !this.job.location || !this.job.description || !this.requirementsStr || !assessmentStartAt || !assessmentEndAt) {
      this.submitError.set('Please fill all fields before creating the role.');
      return;
    }

    if (new Date(assessmentEndAt) <= new Date(assessmentStartAt)) {
      this.submitError.set('Assessment window end must be after start.');
      return;
    }

    const requirements = this.requirementsStr.split(',').map(r => r.trim()).filter(r => r);

    try {
      this.saving.set(true);
      const createdJob = await this.dataService.addJob({
        ...this.job,
        assessmentStartAt,
        assessmentEndAt,
        status: 'Active',
        requirements,
        questionBlueprint: this.questionBlueprint.map((item) => ({
          stage: item.stage,
          count: Math.max(1, Math.min(20, Math.trunc(Number(item.count) || 1))),
        })),
      });
      await this.router.navigate(['/jobs', createdJob.id, 'candidates'], {
        queryParams: {
          autorun: 1,
        },
      });
    } catch {
      this.submitError.set(this.dataService.errorMessage() ?? 'Unable to create role. Please try again.');
    } finally {
      this.saving.set(false);
    }
  }

  private composeDateTime(date: string, time: string): string {
    if (!date || !time) {
      return '';
    }

    return `${date}T${time}`;
  }
}
