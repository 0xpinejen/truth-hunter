import './globals.css';
import type { Metadata } from 'next';
export const metadata: Metadata = { title:'TruthHunter · 真相猎手',description:'别急着相信，先看看证据。' };
export default function RootLayout({children}:{children:React.ReactNode}){return <html lang="zh-CN"><body>{children}</body></html>}
