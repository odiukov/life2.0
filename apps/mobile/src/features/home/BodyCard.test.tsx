import React from 'react';
import { render } from '@testing-library/react-native';
import { ThemeProvider } from '@life-agents/ui';
import { BodyCard } from './BodyCard';
import type { FeaturedBody } from './useHomeSummary';

function wrap(ui: React.ReactElement) {
  return render(<ThemeProvider>{ui}</ThemeProvider>);
}

const fullData: FeaturedBody = {
  weightKg: 78.4,
  weightDelta30d: -1.2,
  weightDeltaPrev: -0.3,
  ageDaysLabel: '3 days ago',
  source: 'ViHealth',
  sparkWeights: [79.6, 79.2, 78.9, 78.7, 78.5, 78.4],
  fatPct: 22.1,
  fatPctDelta30d: -0.8,
  muscleKg: 38.5,
  muscleKgDelta30d: 0.1,
  leanKg: 61.1,
  leanKgDelta30d: -0.4,
};

describe('BodyCard', () => {
  it('renders nothing when data is null', () => {
    const { toJSON } = wrap(<BodyCard data={null} onPress={() => {}} />);
    expect(toJSON()).toBeNull();
  });

  it('renders weight, delta caption, and source on full data', () => {
    const { getByText } = wrap(<BodyCard data={fullData} onPress={() => {}} />);
    getByText('Body');
    getByText('3 days ago · ViHealth');
    getByText('78.4 kg');
    getByText(/↓.*0\.3.*kg/);
    getByText(/−1\.2 kg · 30d/);
    // Footer stat cells
    getByText('FAT');
    getByText('MUSCLE');
    getByText('LEAN');
    getByText('22.1 %');
    getByText('38.5 kg');
    getByText('61.1 kg');
  });

  it('omits weight delta caption when weightDelta30d is null', () => {
    const data = { ...fullData, weightDelta30d: null };
    const { queryByText } = wrap(<BodyCard data={data} onPress={() => {}} />);
    // Hero weight delta caption (e.g. "−1.2 kg · 30d") should be gone.
    // Stat-cell "30d" labels remain — they describe the fat/muscle/lean deltas.
    expect(queryByText(/−.*kg · 30d/)).toBeNull();
    expect(queryByText(/\+.*kg · 30d/)).toBeNull();
  });

  it('hides footer when fat, muscle, and lean are all null', () => {
    const data: FeaturedBody = {
      ...fullData,
      fatPct: null,
      fatPctDelta30d: null,
      muscleKg: null,
      muscleKgDelta30d: null,
      leanKg: null,
      leanKgDelta30d: null,
    };
    const { queryByText } = wrap(<BodyCard data={data} onPress={() => {}} />);
    expect(queryByText('FAT')).toBeNull();
    expect(queryByText('MUSCLE')).toBeNull();
    expect(queryByText('LEAN')).toBeNull();
  });

  it('hides individual cells when their value is null but renders others', () => {
    const data: FeaturedBody = {
      ...fullData,
      muscleKg: null,
      muscleKgDelta30d: null,
    };
    const { getByText, queryByText } = wrap(<BodyCard data={data} onPress={() => {}} />);
    getByText('FAT');
    expect(queryByText('MUSCLE')).toBeNull();
    getByText('LEAN');
  });

  it('shows ↑ arrow when prev delta is positive', () => {
    const data: FeaturedBody = { ...fullData, weightDeltaPrev: 0.5 };
    const { getByText } = wrap(<BodyCard data={data} onPress={() => {}} />);
    getByText(/↑.*0\.5.*kg/);
  });

  it('hides arrow when prev delta is null', () => {
    const data: FeaturedBody = { ...fullData, weightDeltaPrev: null };
    const { queryByText } = wrap(<BodyCard data={data} onPress={() => {}} />);
    expect(queryByText(/[↑↓]/)).toBeNull();
  });
});
