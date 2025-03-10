from .. import gitcmds
from ..i18n import N_
from ..interaction import Interaction

try:
    import gitlab
except ImportError:
    gitlab = None


def create_merge_request(context):
    """Launch a dialog for creating Merge/Pull Requests"""
    forge_remotes = gitcmds.forge_remotes(context)
    if not forge_remotes:
        Interaction.information(
            N_('Cannot Create Merge Requests'),
            N_(
                'No remotes are associated with a forge.\n\n'
                'Use "File > Edit Forges..." to configure forges.\n'
                'Use "File > Edit Remotes..." to associate forges with remotes.'
            ),
        )
        return

    remotes = set(forge_remotes.values())
    forge_details = gitcmds.get_forge_details(context, set(forge_remotes.values()))
    forge = forge_details['gitlab']

    gitlab_api = gitlab.Gitlab(url=forge.url, private_token=forge.token)

    for project in gitlab_api.projects.list(owned=True, iterator=True):
        project.pprint()
        break
