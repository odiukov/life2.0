import { resolveWorkoutIcon } from './workoutIcon';

describe('resolveWorkoutIcon', () => {
  test.each([
    [['strength', ''],          'phosphor:Barbell'],
    [['weights', ''],           'phosphor:Barbell'],
    [['hiit', ''],              'phosphor:Lightning'],
    [['interval', ''],          'phosphor:Lightning'],
    [['', 'HighIntensity'],     'phosphor:Lightning'],
    [['cycling', ''],           'phosphor:PersonSimpleBike'],
    [['', 'gravel ride'],       'phosphor:PersonSimpleBike'],
    [['running', ''],           'phosphor:PersonSimpleRun'],
    [['walking', ''],           'phosphor:PersonSimpleWalk'],
    [['swimming', ''],          'phosphor:PersonSimpleSwim'],
    [['boxing', ''],            'phosphor:BoxingGlove'],
    [['yoga', ''],              'phosphor:PersonSimpleTaiChi'],
    [['pilates', ''],           'phosphor:PersonSimpleTaiChi'],
    [['mind', ''],              'phosphor:PersonSimpleTaiChi'],
    [['hiking', ''],            'phosphor:PersonSimpleHike'],
    [['skiing', ''],            'phosphor:PersonSimpleSki'],
    [['snowboard', ''],         'phosphor:PersonSimpleSnowboard'],
    [['stairs', ''],            'phosphor:Stairs'],
    [['climbing', ''],          'phosphor:Stairs'],
    [['cardio', ''],            'phosphor:Heartbeat'],
    [['elliptical', ''],        'phosphor:Heartbeat'],
    [['soccer', ''],            'phosphor:SoccerBall'],
    [['football', ''],          'phosphor:SoccerBall'],
    [['basketball', ''],        'phosphor:Basketball'],
    [['tennis', ''],            'phosphor:TennisBall'],
    [['golf', ''],              'phosphor:Golf'],
    [['rowing', ''],            'custom:rowing'],
    [['martial arts', ''],      'custom:martial'],
    [['karate', ''],            'custom:martial'],
    [['judo', ''],              'custom:martial'],
    [['dance', ''],             'custom:dance'],
    [['unknown', ''],           'phosphor:Barbell'],
  ] as const)('matches type=%j name=%j to %s', ([type, name], expected) => {
    expect(resolveWorkoutIcon(type, name)).toBe(expected);
  });
});
