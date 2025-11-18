import {
  JupyterFrontEnd,
  JupyterFrontEndPlugin
} from '@jupyterlab/application';
import { FileBrowser, IFileBrowserFactory } from '@jupyterlab/filebrowser';
import { Notification } from '@jupyterlab/apputils';
import { PageConfig } from '@jupyterlab/coreutils';
import { Contents } from '@jupyterlab/services';
import { buildIcon } from '@jupyterlab/ui-components';

const COMMAND_ID = 'jupyter-myst-build-proxy:build-myst';

const getMystConfigFileIfSelected = (fileBrowserWidget: FileBrowser | null): Contents.IModel | false => {
  if (fileBrowserWidget === null) {
    return false;
  }

  const item = fileBrowserWidget.selectedItems().next();
  if (item.value && item.value.name === 'myst.yml') {
    return item.value;
  } else {
    return false;
  }
}

const plugin: JupyterFrontEndPlugin<void> = {
  id: 'jupyter-myst-build-proxy:plugin',
  description:
    'A JupyterLab extension that enables building and viewing a MyST site from the `/myst-build` path.',
  autoStart: true,
  requires: [IFileBrowserFactory],
  activate: (app: JupyterFrontEnd, factory: IFileBrowserFactory) => {
    const { commands, contextMenu } = app;

    commands.addCommand(COMMAND_ID, {
      label: 'Build MyST project',
      caption: 'Build and view the MyST site',
      icon: buildIcon,
      isVisible: () => {
        return !!getMystConfigFileIfSelected(factory.tracker.currentWidget);
      },
      execute: () => {
        const file = getMystConfigFileIfSelected(factory.tracker.currentWidget);
        if (file === false) {
          return;
        }

        // Extract parent directory from file path
        // e.g., "/foo/bar/myst.yml" -> "/foo/bar"
        const parentDir = file.path.substring(0, file.path.lastIndexOf('/'));

        // Construct URL from JupyterLab base URL and parent directory of MyST project file
        const baseUrl = PageConfig.getBaseUrl();
        const mystBaseUrl = parentDir ? `${baseUrl}myst-build/${parentDir}` : `${baseUrl}myst-build` 
        const mystBuildUrl = `${mystBaseUrl}/?rebuild=1`

        const newWindow = window.open(mystBuildUrl, '_blank');

        if (!newWindow) {
          Notification.error(
            `Failed to open MyST build window (${mystBuildUrl}). Please check your popup blocker settings.`
          );
        }
      }
    });

    // Add command to file browser context menu
    contextMenu.addItem({
      command: COMMAND_ID,
      selector: '.jp-DirListing-item[data-isdir="false"]',
      rank: 0
    });
  }
};

export default plugin;
