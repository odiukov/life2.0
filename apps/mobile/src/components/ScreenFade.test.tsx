import React from 'react';
import { Text } from 'react-native';
import { render, screen } from '@testing-library/react-native';
import { ScreenFade } from './ScreenFade';

test('renders children', () => {
  render(
    <ScreenFade>
      <Text>hello</Text>
    </ScreenFade>,
  );
  expect(screen.getByText('hello')).toBeTruthy();
});
