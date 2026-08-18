import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { App } from './App';
import { formatTokens } from './components/dashboard/TokenMetricCards';

describe('CodexUU 1.0 Architecture & Frontend Tests', () => {
  it('formats token numbers with correct suffixes', () => {
    expect(formatTokens(500)).toBe('500');
    expect(formatTokens(1500)).toBe('1.5k');
    expect(formatTokens(2_400_000)).toBe('2.40M');
    expect(formatTokens(1_200_000_000)).toBe('1.20B');
  });

  it('renders dual-channel TopNav correctly', async () => {
    render(<App />);
    await waitFor(() => expect(screen.getAllByText('CodexUU').length).toBeGreaterThan(0));
    expect(screen.getByText('Codex 官方')).toBeDefined();
    expect(screen.getAllByText('Antigravity').length).toBeGreaterThan(0);
    expect(screen.getByText('全部聚合')).toBeDefined();
  });

  it('renders Scheme C Quota Compass and 4 Token Metric Cards', async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByText('额度使用情况')).toBeDefined());
    expect(screen.getByText('今日用量')).toBeDefined();
    expect(screen.getByText('本周用量')).toBeDefined();
    expect(screen.getByText('本月用量')).toBeDefined();
    expect(screen.getByText('累计记录')).toBeDefined();
  });

  it('allows in-place tab switching between Tasks, Trends, Projects, and Skills', async () => {
    render(<App />);

    // Default tab is 今日任务
    await waitFor(() => expect(screen.getAllByText('进行中').length).toBeGreaterThan(0));
    expect(screen.getAllByText('待处理').length).toBeGreaterThan(0);
    expect(screen.getAllByText('已完成').length).toBeGreaterThan(0);

    // Switch to 用量趋势
    const trendsTabBtn = screen.getByText('用量趋势');
    fireEvent.click(trendsTabBtn);
    await waitFor(() => expect(screen.getByText('趋势折线图 (0 基线)')).toBeDefined());

    // Switch to 项目排行
    const projectsTabBtn = screen.getByText('项目排行');
    fireEvent.click(projectsTabBtn);
    await waitFor(() => expect(screen.getByText('项目用量排行')).toBeDefined());
    expect(screen.getByText('活动概览指标')).toBeDefined();

    // Switch to Skill & 工具
    const skillsTabBtn = screen.getByText('Skill & 工具');
    fireEvent.click(skillsTabBtn);
    await waitFor(() => expect(screen.getByText('Skill 与工具真实调用')).toBeDefined());
  });
});
