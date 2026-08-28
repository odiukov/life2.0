import Sleep from './generated/Sleep';
import Workout from './generated/Workout';
import Nutrition from './generated/Nutrition';
import Mood from './generated/Mood';
import Habits from './generated/Habits';
import Recovery from './generated/Recovery';
import Medication from './generated/Medication';
import Finance from './generated/Finance';
import Calendar from './generated/Calendar';
import Home from './generated/Home';
import Body from './generated/Body';

export const agentIcons = {
  sleep: Sleep,
  workout: Workout,
  nutrition: Nutrition,
  mood: Mood,
  habits: Habits,
  recovery: Recovery,
  medication: Medication,
  finance: Finance,
  calendar: Calendar,
  home: Home,
  body: Body,
} as const;
