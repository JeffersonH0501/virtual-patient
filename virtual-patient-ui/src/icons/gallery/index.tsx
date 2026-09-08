import '../../index.css';
import {ComponentType} from 'react';
import {createRoot} from 'react-dom/client';
import {IconProps} from '..';

type IconModule = Record<string, unknown>;

const iconModules = import.meta.glob<IconModule>('../*.tsx', {eager: true});

const icons = Object.values(iconModules)
  .flatMap((iconModule) => Object.entries(iconModule))
  .filter((entry): entry is [string, ComponentType<IconProps>] => typeof entry[1] === 'function')
  .sort(([firstName], [secondName]) => firstName.localeCompare(secondName));

export const IconGallery = () => (
  <main className="icon-gallery">
    <header>
      <p>Virtual Patient UI</p>
      <h1>Icon gallery</h1>
      <span>{icons.length} components from src/icons</span>
    </header>
    <section>
      {icons.map(([name, Icon]) => (
        <article key={name}>
          <div className={`icon-guide ${name === 'LogoIcon' ? 'logo-guide' : ''}`}>
            <div className="size-boundary">
              <div className="icon-preview">
                <Icon color="currentColor" />
              </div>
            </div>
          </div>
          <code>{name}</code>
        </article>
      ))}
    </section>
  </main>
);

createRoot(document.getElementById('root')!).render(<IconGallery />);
