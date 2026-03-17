import nextVitals from 'eslint-config-next/core-web-vitals'

const config = [
	{
		ignores: ['node_modules/**', '.next/**', 'dist/**', 'build/**', 'coverage/**', 'next-env.d.ts'],
	},
	...nextVitals,
]

export default config
