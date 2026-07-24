import {HttpClient, HttpHeaders} from '@angular/common/http';
import {Injectable, inject} from '@angular/core';
import {firstValueFrom} from 'rxjs';

import {AuthService} from './auth.service';
import {DataService} from './data.service';

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

interface AIChatResponse {
  reply: string;
  model: string;
  fallback_used: boolean;
}

@Injectable({
  providedIn: 'root',
})
export class AssistantService {
  private readonly http = inject(HttpClient);
  private readonly authService = inject(AuthService);
  private readonly dataService = inject(DataService);

  private resolveOrchUrl(): string {
    const envValue = (globalThis as {ORCHESTRATION_API_BASE_URL?: string}).ORCHESTRATION_API_BASE_URL;
    if (envValue) {
      return envValue;
    }

    if (typeof localStorage !== 'undefined') {
      const persisted = localStorage.getItem('talentos.orchestration.baseUrl');
      if (persisted) {
        return persisted;
      }
    }

    return 'http://127.0.0.1:8001';
  }

  async answer(prompt: string, history: ChatMessage[] = []): Promise<string> {
    const normalized = prompt.trim();
    if (!normalized) {
      return 'Please enter a question and I can help with candidates, roles, assessments, and pipeline decisions.';
    }

    const jobs = this.dataService.jobs();
    const candidates = this.dataService.candidates();
    const activeJobs = jobs.filter((job) => job.status === 'Active').length;
    const pipelineSummary: Record<string, number> = {};
    for (const candidate of candidates) {
      pipelineSummary[candidate.status] = (pipelineSummary[candidate.status] ?? 0) + 1;
    }

    const topCandidates = candidates
      .slice()
      .sort((left, right) => right.matchScore - left.matchScore)
      .slice(0, 5)
      .map((candidate) => ({
        name: candidate.name,
        role: candidate.role,
        match_score: candidate.matchScore,
        status: candidate.status,
        source: candidate.source ?? null,
      }));

    const allCandidates = candidates
      .slice()
      .sort((left, right) => right.matchScore - left.matchScore)
      .slice(0, 50)
      .map((candidate) => ({
        name: candidate.name,
        role: candidate.role,
        match_score: candidate.matchScore,
        status: candidate.status,
        source: candidate.source ?? null,
      }));

    const candidatesByRole = jobs
      .filter((job) => job.status === 'Active')
      .map((job) => ({
        role: job.title,
        candidates: candidates
          .filter((candidate) => candidate.role === job.title)
          .sort((left, right) => right.matchScore - left.matchScore)
          .slice(0, 10)
          .map((candidate) => ({
            name: candidate.name,
            match_score: candidate.matchScore,
            status: candidate.status,
            source: candidate.source ?? null,
          })),
      }));

    const jobsOverview = jobs
      .filter((job) => job.status === 'Active')
      .map((job) => ({
        title: job.title,
        department: job.department,
        location: job.location,
        candidates_count: job.candidatesCount,
      }));

    const assessmentSummary = await this.safeLoadAssessmentSummary();

    const context = {
      active_jobs: activeJobs,
      total_candidates: candidates.length,
      pipeline_summary: pipelineSummary,
      top_candidates: topCandidates,
      candidates: allCandidates,
      candidates_by_role: candidatesByRole,
      jobs_overview: jobsOverview,
      assessment_summary: assessmentSummary,
    };

    const messages: ChatMessage[] = [
      ...history.slice(-8),
      {role: 'user' as const, content: normalized},
    ];

    const token = this.authService.accessToken();
    const headers = token ? new HttpHeaders({Authorization: `Bearer ${token}`}) : new HttpHeaders();
    const orchUrl = this.resolveOrchUrl();

    try {
      const response = await firstValueFrom(
        this.http.post<AIChatResponse>(
          `${orchUrl}/ai/chat`,
          {messages, context},
          {headers},
        ),
      );
      return response.reply;
    } catch (error) {
      const candidate = error as {error?: {error?: {message?: string}; detail?: string}; message?: string};
      const message = candidate.error?.error?.message
        || candidate.error?.detail
        || candidate.message
        || 'Unable to get an answer from Gemini right now.';
      throw new Error(message);
    }
  }

  private async safeLoadAssessmentSummary(): Promise<{report_ready: number; terminated: number}> {
    try {
      const reports = await this.dataService.getAssessmentReportSummaries();
      return {
        report_ready: reports.filter((item) => item.reportAvailable).length,
        terminated: reports.filter((item) => item.sessionStatus === 'TERMINATED').length,
      };
    } catch {
      return {
        report_ready: 0,
        terminated: 0,
      };
    }
  }
}
