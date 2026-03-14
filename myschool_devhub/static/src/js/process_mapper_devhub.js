/** @odoo-module */

import { registry } from "@web/core/registry";
import { patch } from "@web/core/utils/patch";
import { user } from "@web/core/user";
import { useState, onWillStart } from "@odoo/owl";

// Get the ProcessMapperClient from the actions registry
const ProcessMapperClient = registry.category("actions").get("process_mapper_canvas");
const { ProcessMapperProperties } = ProcessMapperClient.components;

// -------------------------------------------------------------------
// Patch ProcessMapperClient: user story loading & management
// -------------------------------------------------------------------
patch(ProcessMapperClient.prototype, {
    setup() {
        super.setup();
        this.state.userStories = [];
        this.state.devhubProjects = [];

        onWillStart(async () => {
            await this._loadDevhubProjects();
        });
    },

    async _loadDevhubProjects() {
        try {
            const projects = await this.orm.searchRead(
                "devhub.project",
                [["is_active", "=", true]],
                ["name"],
                { limit: 200, order: "name" },
            );
            this.state.devhubProjects = projects;
        } catch {
            // devhub module data might not be accessible
        }
    },

    async onSearchStories(query) {
        try {
            const stories = await this.orm.call(
                "process.map", "search_user_stories",
                [query || ''],
            );
            this.state.userStories = stories;
        } catch {
            this.state.userStories = [];
        }
    },

    async onCreateStory(name, projectId) {
        try {
            const story = await this.orm.call(
                "process.map", "create_user_story",
                [name, projectId],
            );
            const el = this.getSelectedElement();
            if (el) {
                el.devhub_item_id = story.id;
                el.devhub_item_name = story.name;
                this.state.dirty = true;
                this._pushHistory();
            }
            return story;
        } catch (e) {
            this.notification.add(
                "Failed to create story: " + (e.message || e),
                { type: "danger" },
            );
        }
    },

    onLinkStory(storyId, storyName) {
        const el = this.getSelectedElement();
        if (!el) return;
        el.devhub_item_id = storyId;
        el.devhub_item_name = storyName;
        this.state.dirty = true;
        this._pushHistory();
    },

    onUnlinkStory() {
        const el = this.getSelectedElement();
        if (!el) return;
        el.devhub_item_id = false;
        el.devhub_item_name = '';
        this.state.dirty = true;
        this._pushHistory();
    },

    // --- Context menu: flat User Story items ---
    getContextMenuItems() {
        const items = super.getContextMenuItems();
        const step = this._getContextMenuStep();
        if (step && (step.step_type === 'task' || step.step_type === 'subprocess')) {
            if (step.devhub_item_id) {
                // Story linked: two flat actions
                items.unshift(
                    {
                        id: 'unlink_user_story',
                        label: 'Unlink User Story',
                        icon: 'fa-chain-broken',
                    },
                    {
                        id: 'edit_user_story',
                        label: 'Edit User Story',
                        icon: 'fa-bookmark',
                    },
                );
            } else {
                // No story: open form dialog
                items.unshift({
                    id: 'new_user_story',
                    label: 'New User Story',
                    icon: 'fa-bookmark-o',
                });
            }
        }
        return items;
    },

    onContextMenuAction(itemId) {
        if (itemId === 'new_user_story') {
            this.onCtxNewStory();
            return;
        }
        if (itemId === 'edit_user_story') {
            this.onCtxEditStory();
            return;
        }
        if (itemId === 'unlink_user_story') {
            this.onCtxUnlinkStory();
            return;
        }
        return super.onContextMenuAction(itemId);
    },

    async onCtxNewStory() {
        const step = this._getContextMenuStep();
        if (!step) return;
        const stepId = step.id;
        const openedAt = new Date().toISOString().replace('T', ' ').slice(0, 19);
        this.closeContextMenu();

        await this.actionService.doAction({
            type: 'ir.actions.act_window',
            res_model: 'devhub.item',
            views: [[false, 'form']],
            target: 'new',
            context: {
                default_item_type: 'story',
            },
        }, {
            onClose: async () => {
                // Find story created after dialog was opened
                try {
                    const stories = await this.orm.searchRead(
                        'devhub.item',
                        [
                            ['item_type', '=', 'story'],
                            ['create_uid', '=', user.userId],
                            ['create_date', '>=', openedAt],
                        ],
                        ['id', 'display_name'],
                        { limit: 1, order: 'create_date desc' },
                    );
                    if (stories.length > 0) {
                        const s = this.state.steps.find(st => st.id === stepId);
                        if (s && !s.devhub_item_id) {
                            s.devhub_item_id = stories[0].id;
                            s.devhub_item_name = stories[0].display_name;
                            this.state.dirty = true;
                            this._pushHistory();
                        }
                    }
                } catch {
                    // silently ignore
                }
            },
        });
    },

    async onCtxEditStory() {
        const step = this._getContextMenuStep();
        if (!step || !step.devhub_item_id) return;
        const storyId = step.devhub_item_id;
        const stepId = step.id;
        this.closeContextMenu();

        await this.actionService.doAction({
            type: 'ir.actions.act_window',
            res_model: 'devhub.item',
            res_id: storyId,
            views: [[false, 'form']],
            target: 'new',
        }, {
            onClose: async () => {
                // Refresh display name in case it changed
                try {
                    const records = await this.orm.searchRead(
                        'devhub.item',
                        [['id', '=', storyId]],
                        ['display_name'],
                        { limit: 1 },
                    );
                    if (records.length > 0) {
                        const s = this.state.steps.find(st => st.id === stepId);
                        if (s) {
                            s.devhub_item_name = records[0].display_name;
                        }
                    }
                } catch {
                    // silently ignore
                }
            },
        });
    },

    onCtxUnlinkStory() {
        const step = this._getContextMenuStep();
        if (!step) return;
        this.closeContextMenu();
        step.devhub_item_id = false;
        step.devhub_item_name = '';
        this.state.dirty = true;
        this._pushHistory();
    },
});

// -------------------------------------------------------------------
// Patch ProcessMapperProperties: user story selector
// -------------------------------------------------------------------
const origProps = { ...ProcessMapperProperties.props };
ProcessMapperProperties.props = {
    ...origProps,
    userStories: { type: Array, optional: true },
    devhubProjects: { type: Array, optional: true },
    onSearchStories: { type: Function, optional: true },
    onCreateStory: { type: Function, optional: true },
    onLinkStory: { type: Function, optional: true },
    onUnlinkStory: { type: Function, optional: true },
};

patch(ProcessMapperProperties.prototype, {
    setup() {
        super.setup();
        this.storyState = useState({
            searchQuery: '',
            showResults: false,
            showCreateForm: false,
            newStoryName: '',
            selectedProjectId: false,
        });
        this._searchTimeout = null;
    },

    onStorySearchInput(ev) {
        const query = ev.target.value;
        this.storyState.searchQuery = query;

        if (this._searchTimeout) clearTimeout(this._searchTimeout);
        this._searchTimeout = setTimeout(async () => {
            if (query.length >= 2 && this.props.onSearchStories) {
                await this.props.onSearchStories(query);
                this.storyState.showResults = true;
            } else {
                this.storyState.showResults = false;
            }
        }, 300);
    },

    onStorySearchFocus() {
        if (this.storyState.searchQuery.length >= 2) {
            this.storyState.showResults = true;
        }
    },

    onStorySelect(story) {
        if (this.props.onLinkStory) {
            this.props.onLinkStory(story.id, story.name);
        }
        this.storyState.showResults = false;
        this.storyState.searchQuery = '';
    },

    onStoryClear() {
        if (this.props.onUnlinkStory) {
            this.props.onUnlinkStory();
        }
    },

    toggleCreateStoryForm() {
        this.storyState.showCreateForm = !this.storyState.showCreateForm;
        this.storyState.showResults = false;
    },

    onNewStoryNameChange(ev) {
        this.storyState.newStoryName = ev.target.value;
    },

    onNewStoryProjectChange(ev) {
        this.storyState.selectedProjectId = ev.target.value ? parseInt(ev.target.value) : false;
    },

    async onCreateNewStory() {
        const name = this.storyState.newStoryName.trim();
        const projectId = this.storyState.selectedProjectId;
        if (!name || !projectId) return;

        await this.props.onCreateStory(name, projectId);
        this.storyState.showCreateForm = false;
        this.storyState.newStoryName = '';
        this.storyState.selectedProjectId = false;
    },
});

