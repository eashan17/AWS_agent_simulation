// A small stroke icon set (24 px grid, 1.75 stroke), drawn for this product.
const base = { width: 18, height: 18, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.75, strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': true }
const I = (paths) => function Icon({ size = 18, className, ...rest }) {
  return <svg {...base} width={size} height={size} className={className} {...rest}>{paths}</svg>
}

export const IconOverview = I(<><rect x="3.5" y="3.5" width="7" height="7" rx="2" /><rect x="13.5" y="3.5" width="7" height="7" rx="2" /><rect x="3.5" y="13.5" width="7" height="7" rx="2" /><rect x="13.5" y="13.5" width="7" height="7" rx="2" /></>)
export const IconSetup = I(<><path d="M5 4h10l4 4v12H5z" /><path d="M15 4v4h4" /><path d="M8.5 12.5h7M8.5 16h5" /></>)
export const IconSim = I(<><circle cx="7" cy="8" r="2.5" /><circle cx="17" cy="16" r="2.5" /><path d="M9 9.5c3 1 4 4 6 5" strokeDasharray="2 2.5" /><path d="M4 20h16" /></>)
export const IconAnalysis = I(<><path d="M4 19h16" /><path d="M5 15l4-5 4 3 6-7" /><circle cx="19" cy="6" r="1.5" /></>)
export const IconRuns = I(<><path d="M8 6h12M8 12h12M8 18h12" /><circle cx="4" cy="6" r="1" /><circle cx="4" cy="12" r="1" /><circle cx="4" cy="18" r="1" /></>)
export const IconArrow = I(<><path d="M5 12h14" /><path d="M13 6l6 6-6 6" /></>)
export const IconBack = I(<><path d="M19 12H5" /><path d="M11 6l-6 6 6 6" /></>)
export const IconCheck = I(<path d="M5 12.5l4.5 4.5L19 7.5" />)
export const IconX = I(<><path d="M6 6l12 12M18 6L6 18" /></>)
export const IconAlert = I(<><path d="M12 4l9 16H3z" /><path d="M12 10v4.5M12 17.5v.01" /></>)
export const IconGear = I(<><circle cx="12" cy="12" r="3" /><path d="M12 3v2.5M12 18.5V21M3 12h2.5M18.5 12H21M5.6 5.6l1.8 1.8M16.6 16.6l1.8 1.8M5.6 18.4l1.8-1.8M16.6 7.4l1.8-1.8" /></>)
export const IconBolt = I(<path d="M13 3L5 13.5h6L10 21l8-10.5h-6z" />)
export const IconClock = I(<><circle cx="12" cy="12" r="8.5" /><path d="M12 7.5V12l3 2" /></>)
export const IconPlay = I(<path d="M8 5.5v13l10.5-6.5z" fill="currentColor" stroke="none" />)
export const IconPause = I(<><rect x="7" y="5.5" width="3.5" height="13" rx="1" fill="currentColor" stroke="none" /><rect x="13.5" y="5.5" width="3.5" height="13" rx="1" fill="currentColor" stroke="none" /></>)
export const IconRestart = I(<><path d="M4.5 12a7.5 7.5 0 1 0 2.2-5.3" /><path d="M4.5 4.5v4h4" /></>)
export const IconSkip = I(<><path d="M5 5.5v13l9-6.5z" fill="currentColor" stroke="none" /><path d="M18 5.5v13" strokeWidth="2.5" /></>)
export const IconFlag = I(<><path d="M5 21V4" /><path d="M5 4h11l-2 4 2 4H5" /></>)
export const IconSpark = I(<><path d="M12 3v4M12 17v4M3 12h4M17 12h4" /><path d="M12 8l1.5 2.5L16 12l-2.5 1.5L12 16l-1.5-2.5L8 12l2.5-1.5z" /></>)
export const IconSearch = I(<><circle cx="11" cy="11" r="6.5" /><path d="M20 20l-4.2-4.2" /></>)
export const IconSplit = I(<><path d="M12 4v16" /><rect x="3.5" y="6" width="6" height="12" rx="2" /><rect x="14.5" y="6" width="6" height="12" rx="2" /></>)
export const IconChain = I(<><path d="M10 14l4-4" /><path d="M8.5 16.5l-1 1a3 3 0 0 1-4.2-4.2l3-3a3 3 0 0 1 4.2 0" /><path d="M15.5 7.5l1-1a3 3 0 0 1 4.2 4.2l-3 3a3 3 0 0 1-4.2 0" /></>)
export const IconPeople = I(<><circle cx="9" cy="8" r="3" /><path d="M3.5 19a5.5 5.5 0 0 1 11 0" /><circle cx="17" cy="9" r="2.3" /><path d="M15.5 14.2A4.5 4.5 0 0 1 21 18.5" /></>)
export const IconLock = I(<><rect x="5" y="10.5" width="14" height="10" rx="2.5" /><path d="M8 10.5V8a4 4 0 0 1 8 0v2.5" /></>)
export const IconWave = I(<path d="M3 14c2.5 0 2.5-4 5-4s2.5 4 5 4 2.5-4 5-4 2.5 4 3 4" />)
export const IconQuote = I(<><path d="M9 7c-2.5 1-4 3-4 6v4h5v-5H7.5" /><path d="M19 7c-2.5 1-4 3-4 6v4h5v-5h-2.5" /></>)
export const IconMenu = I(<><path d="M4 7h16M4 12h16M4 17h16" /></>)
