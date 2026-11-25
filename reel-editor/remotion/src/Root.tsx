import React from 'react';
import {Composition} from 'remotion';
import {Scoreboard, scoreboardDefaults} from './Scoreboard';
import {GoalMeter, meterDefaults} from './GoalMeter';
import {Card, cardDefaults} from './Card';
import {HookTitle, hookDefaults} from './HookTitle';

// Every composition is 1080x1920 @30 with a transparent background. render.py renders them as PNG sequences
// (props passed per reel from edit.json "remotion" entries) and overlays them at their start time.
const dur = ({props}: {props: any}) => ({durationInFrames: Math.max(1, Math.round((props.dur ?? 10) * 30))});

export const Root: React.FC = () => (
  <>
    <Composition id="Scoreboard" component={Scoreboard as any} width={1080} height={1920} fps={30}
                 durationInFrames={300} defaultProps={scoreboardDefaults} calculateMetadata={dur} />
    <Composition id="GoalMeter" component={GoalMeter as any} width={1080} height={1920} fps={30}
                 durationInFrames={300} defaultProps={meterDefaults} calculateMetadata={dur} />
    <Composition id="HookTitle" component={HookTitle as any} width={1080} height={1920} fps={30}
                 durationInFrames={60} defaultProps={hookDefaults} calculateMetadata={dur} />
    <Composition id="Card" component={Card as any} width={1080} height={1920} fps={30}
                 durationInFrames={90} defaultProps={cardDefaults} calculateMetadata={dur} />
  </>
);
