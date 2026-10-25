import './globals.css';
import './reference-ui.css';
import type { Metadata } from 'next';
export const metadata: Metadata = { title:'TruthHunter 2.0 · 真相猎手',icons:{icon:'/truthhunter.svg'},description:'别急着相信，先看看证据。' };
export default function RootLayout({children}:{children:React.ReactNode}){return <html lang="zh-CN"><body>{children}</body></html>}
