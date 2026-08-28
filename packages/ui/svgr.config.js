module.exports = {
  typescript: true,
  native: true,
  icon: true,
  replaceAttrValues: { '#000': 'currentColor' },
  svgProps: { fill: 'none', stroke: 'currentColor', strokeWidth: 2, strokeLinecap: 'round', strokeLinejoin: 'round' },
  svgoConfig: {
    plugins: [
      { name: 'preset-default', params: { overrides: { removeViewBox: false } } },
      { name: 'removeAttrs', params: { attrs: 'xmlns' } },
    ],
  },
};
