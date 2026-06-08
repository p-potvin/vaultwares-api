import { useState } from 'react';
import { Shell } from '../components/Shell';
import { Card } from '../components/Card';
import { Button } from '../components/Button';
import { Led } from '../components/Led';
import { IconServer, IconShield, IconDocument } from '../icons/VaultWaresIcons';

export function DemoPage() {
  const [mode, setMode] = useState<'console' | 'warm'>('console');

  const toggleMode = () => setMode(m => m === 'console' ? 'warm' : 'console');

  return (
    <Shell mode={mode} className="p-8">
      <div className="max-w-5xl mx-auto space-y-8">
        
        {/* Header */}
        <header className="flex justify-between items-center pb-8 border-b border-[var(--vault-console-border-subtle)]">
          <div className="flex items-center gap-3">
            <IconShield className={mode === 'console' ? 'text-[var(--vault-console-gold)]' : 'text-[#161320]'} />
            <h1 className="text-2xl font-bold tracking-tight">VaultWares Revisited</h1>
            <Led status="online" className="ml-2" />
          </div>
          <Button variant="secondary" mode={mode} onClick={toggleMode}>
            Toggle Mode (Current: {mode})
          </Button>
        </header>

        {/* Grid Layout */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8 pt-4">
          
          {/* Status Card */}
          <Card mode={mode} className="space-y-6">
            <div className="flex items-center gap-2 mb-4">
              <IconServer className="w-5 h-5" />
              <h2 className="text-xl font-semibold">System Diagnostics</h2>
            </div>
            
            <div className="space-y-4 font-mono text-sm">
              <div className="flex justify-between items-center p-3 rounded bg-black/20">
                <span className="flex items-center gap-2"><Led status="online" /> Core Mainframe</span>
                <span className="opacity-70">SECURE</span>
              </div>
              <div className="flex justify-between items-center p-3 rounded bg-black/20">
                <span className="flex items-center gap-2"><Led status="sync" /> Data Sync</span>
                <span className="opacity-70">98%</span>
              </div>
              <div className="flex justify-between items-center p-3 rounded bg-black/20">
                <span className="flex items-center gap-2"><Led status="warning" /> Firewall Relays</span>
                <span className="opacity-70">DEGRADED</span>
              </div>
            </div>
            <div className="flex gap-4 pt-4">
              <Button variant="primary" mode={mode}>Run Diagnostics</Button>
              <Button variant="ghost" mode={mode}>View Logs</Button>
            </div>
          </Card>

          {/* Typography & Elements Card */}
          <Card mode={mode} className="space-y-6">
            <div className="flex items-center gap-2 mb-4">
              <IconDocument className="w-5 h-5" />
              <h2 className="text-xl font-semibold">Typography & Buttons</h2>
            </div>
            
            <div className="space-y-4">
              <p className="leading-relaxed opacity-90">
                This demonstrates the dual-mode capability of the VaultWares-Revisited system. 
                Switching modes does not simply invert colors, but transitions between the 
                active operational surface (Console) and the archival surface (Warm).
              </p>
              
              <div className="flex flex-wrap gap-4 pt-4">
                <Button variant="primary" mode={mode}>Primary Action</Button>
                <Button variant="secondary" mode={mode}>Secondary</Button>
                <Button variant="ghost" mode={mode}>Ghost Link</Button>
              </div>
            </div>
          </Card>

        </div>
      </div>
    </Shell>
  );
}