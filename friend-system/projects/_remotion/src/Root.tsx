import React from 'react';
import {Composition} from 'remotion';
import {SceneFlat, SceneProps} from './SceneFlat';

const brand = {accent: '#FF5A36', accent2: '#FFD2C7', ink: '#111111', paper: '#FFFFFF'};

export const Root: React.FC = () => (
  <>
    <Composition id="SceneFlat" component={SceneFlat as React.FC<any>} width={1080} height={1920} fps={30} durationInFrames={90}
      defaultProps={{frames: 90, layer: 'front', elements: [], brand} as SceneProps}
      calculateMetadata={({props}) => ({durationInFrames: Math.max(1, (props as SceneProps).frames)})} />
  </>
);
