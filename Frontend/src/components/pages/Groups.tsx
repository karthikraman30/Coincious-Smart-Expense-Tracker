import { useState, useEffect } from 'react';
import { User as SupabaseUser } from '@supabase/supabase-js';

type AppUser = SupabaseUser & {
  user_metadata?: {
    full_name?: string;
    avatar_url?: string;
  };
};

declare module '../../contexts/AuthContext' {
  interface AuthContextType {
    user: AppUser | null;
    signIn: (email: string, password: string) => Promise<void>;
    signOut: () => Promise<void>;
  }
}
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { Avatar, AvatarFallback } from '../../components/ui/avatar';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '../../components/ui/dropdown-menu';
import { Input } from '../ui/input';
import { supabase } from '../../utils/supabase/client';
import { useAuth } from '../../App';
import {
  Plus,
  Search,
  Users,
  DollarSign,
  Calendar,
  MoreVertical,
  Trash,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '../ui/dialog';
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '../ui/alert-dialog';
import { Label } from '../ui/label';
import { toast } from 'sonner';

// Groups are now fetched from the API

export function Groups() {
  const [searchTerm, setSearchTerm] = useState('');
  const [newGroupName, setNewGroupName] = useState('');
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [groups, setGroups] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const { user } = useAuth() as { user: AppUser | null };

  // State for delete confirmation
  const [deleteAlertOpen, setDeleteAlertOpen] = useState(false);
  const [groupToDelete, setGroupToDelete] = useState<any | null>(null);

  // Helper function to get user display info
  const getUserDisplayInfo = (user: AppUser | null) => ({
    id: user?.id || '',
    name: user?.user_metadata?.full_name || 'You',
    avatar: user?.user_metadata?.avatar_url ||
      `https://ui-avatars.com/api/?name=${encodeURIComponent(user?.email?.charAt(0).toUpperCase() || 'U')}`
  });

  useEffect(() => {
    const fetchGroups = async () => {
      if (!user) {
        setLoading(false);
        return;
      }

      try {
        setLoading(true);

        const { data: { session }, error: sessionError } = await supabase.auth.getSession();

        if (sessionError) {
          console.error('Error getting session:', sessionError);
          throw new Error('Your session has expired. Please log in again.');
        }

        if (!session?.access_token) {
          throw new Error('No active session. Please log in again.');
        }

        console.log('Fetching groups with fresh token...');
        console.log('Making request to /api/groups...');

        const response = await fetch('http://localhost:8000/api/groups', {
          method: 'GET',
          headers: {
            'Authorization': `Bearer ${session.access_token}`,
            'Content-Type': 'application/json',
          },
          credentials: 'include',
        });

        let responseData;
        try {
          responseData = await response.clone().json();
          console.log('Response data:', responseData);
        } catch (jsonError) {
          const textResponse = await response.text();
          console.error('Failed to parse JSON response:', textResponse);
          throw new Error(`Invalid server response: ${textResponse.substring(0, 200)}`);
        }

        if (!response.ok) {
          console.error('API Error - Status:', response.status, 'Status Text:', response.statusText);
          console.error('Response Headers:', Object.fromEntries(response.headers.entries()));
          console.error('Response Body:', responseData);

          let errorMessage = 'Failed to fetch groups';

          if (responseData) {
            if (responseData.details) {
              errorMessage = `Error: ${responseData.error || 'Unknown error'}`;
              if (process.env.NODE_ENV === 'development') {
                console.error('Error details:', responseData.details);
                if (responseData.trace) {
                  console.error('Server stack trace:', responseData.trace);
                }
              }
            } else if (responseData.error) {
              errorMessage = typeof responseData.error === 'string'
                ? responseData.error
                : JSON.stringify(responseData.error);
            }
          } else {
            errorMessage = `Server returned ${response.status}: ${response.statusText}`;
          }

          throw new Error(errorMessage);
        }

        console.log('Groups data:', responseData);
        const userInfo = getUserDisplayInfo(user);

        const transformedGroups = (responseData.groups || []).map((group: any) => ({
          ...group,
          id: group.id || '',
          name: group.name || 'Unnamed Group',
          created_at: group.created_at || new Date().toISOString(),
          updated_at: group.updated_at || new Date().toISOString(),
          members: [userInfo],
          member_count: group.member_count || 1,
          total_expenses: group.total_expenses || 0,
          yourBalance: 0,
          lastActivity: 'Just now',
          status: 'active' as const
        }));

        setGroups(transformedGroups);
      } catch (error) {
        console.error('Error in fetchGroups:', error);
        const errorMessage = error instanceof Error ? error.message : 'Failed to load groups';
        toast.error(errorMessage, {
          duration: 5000,
          description: 'Please check your connection and try again.'
        });
      } finally {
        setLoading(false);
      }
    };

    fetchGroups();
  }, [user]);

  const filteredGroups = groups.filter(group =>
    group.name.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const handleCreateGroup = async () => {
    if (!newGroupName.trim()) {
      toast.error('Please enter a group name');
      return;
    }

    if (!user) {
      toast.error('You must be logged in to create a group');
      return;
    }

    try {
      console.log('Getting session...');
      const { data: { session }, error: sessionError } = await supabase.auth.getSession();

      if (sessionError) {
        console.error('Session error:', sessionError);
        throw new Error('Failed to get session');
      }

      if (!session?.access_token) {
        throw new Error('No active session');
      }

      console.log('Creating group with name:', newGroupName);
      const response = await fetch('http://localhost:8000/api/groups', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${session.access_token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          name: newGroupName,
        }),
      });

      console.log('Response status:', response.status);

      let responseData;
      try {
        responseData = await response.clone().json();
        console.log('Response data:', responseData);
      } catch (jsonError) {
        const textResponse = await response.text();
        console.error('Failed to parse JSON response:', textResponse);
        throw new Error(`Invalid server response: ${textResponse.substring(0, 200)}`);
      }

      if (!response.ok) {
        console.error('API Error - Status:', response.status, 'Status Text:', response.statusText);
        console.error('Response Headers:', Object.fromEntries(response.headers.entries()));
        console.error('Response Body:', responseData);

        let errorMessage = 'Failed to create group';

        if (responseData) {
          if (responseData.details) {
            errorMessage = `Error: ${responseData.error || 'Unknown error'}`;
            console.error('Error details:', responseData.details);
            if (responseData.trace) {
              console.error('Server stack trace:', responseData.trace);
            }
          } else if (responseData.error) {
            errorMessage = typeof responseData.error === 'string'
              ? responseData.error
              : JSON.stringify(responseData.error);
          }
        } else {
          errorMessage = `Server returned ${response.status}: ${response.statusText}`;
        }

        throw new Error(errorMessage);
      }

      const newGroup = responseData.group || responseData;
      console.log('Created group:', newGroup);

      const userInfo = getUserDisplayInfo(user);

      setGroups(prev => [{
        ...newGroup,
        member_count: newGroup.member_count || 1,
        members: [userInfo],
        total_expenses: 0,
        yourBalance: 0,
        lastActivity: 'Just now',
        status: 'active' as const
      }, ...prev]);

      toast.success('Group created successfully!');
      setNewGroupName('');
      setIsCreateDialogOpen(false);
    } catch (error) {
      console.error('Error in handleCreateGroup:', error);
      const errorMessage = error instanceof Error ? error.message : 'Failed to create group';
      toast.error(errorMessage, {
        duration: 5000,
        description: 'Please check your connection and try again.'
      });
    }
  };

  // Function to handle group deletion
  const handleDeleteGroup = async () => {
    if (!groupToDelete) {
      toast.error('No group selected for deletion.');
      return;
    }

    const loadingToastId = toast.loading(`Deleting group "${groupToDelete.name}"...`);

    try {
      const { data: { session }, error: sessionError } = await supabase.auth.getSession();
      if (sessionError || !session?.access_token) {
        throw new Error('Failed to get session. Please log in again.');
      }

      const response = await fetch(`http://localhost:8000/api/groups/${groupToDelete.id}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${session.access_token}`,
        },
      });

      if (!response.ok) {
        let errorMessage = 'Failed to delete group';
        try {
          const errorData = await response.json();
          errorMessage = errorData.error || errorData.message || errorMessage;
        } catch (e) {
          errorMessage = `Server returned ${response.status}: ${response.statusText}`;
        }
        throw new Error(errorMessage);
      }

      toast.success('Group deleted successfully!', { id: loadingToastId });
      setGroups(prevGroups => prevGroups.filter(g => g.id !== groupToDelete.id));

    } catch (error) {
      console.error('Error in handleDeleteGroup:', error);
      const errorMessage = error instanceof Error ? error.message : 'Failed to delete group';
      toast.error(errorMessage, {
        id: loadingToastId,
        description: 'Please try again.'
      });
    } finally {
      setDeleteAlertOpen(false);
      setGroupToDelete(null);
    }
  };


  return (
    <div className="p-4 md:p-6 space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl md:text-3xl font-bold">Groups</h1>
          <p className="text-muted-foreground">Manage your shared expense groups</p>
        </div>

        <Dialog open={isCreateDialogOpen} onOpenChange={setIsCreateDialogOpen}>
          <DialogTrigger asChild>
            <Button>
              <Plus className="h-4 w-4 mr-2" />
              Create Group
            </Button>
          </DialogTrigger>
          <DialogContent className="sm:max-w-[425px]">
            <DialogHeader>
              <DialogTitle>Create New Group</DialogTitle>
              <DialogDescription>
                Create a new group to start splitting expenses with friends or family.
              </DialogDescription>
            </DialogHeader>
            <div className="grid gap-4 py-4">
              <div className="grid gap-2">
                <Label htmlFor="groupName">Group Name</Label>
                <Input
                  id="groupName"
                  placeholder="e.g., Weekend Trip"
                  value={newGroupName}
                  onChange={(e) => setNewGroupName(e.target.value)}
                />
              </div>
            </div>
            <DialogFooter>
              <Button type="submit" onClick={handleCreateGroup}>
                Create Group
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
        <Input
          placeholder="Search groups..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="pl-10"
        />
      </div>

      {/* Loading State */}
      {loading && (
        <Card>
          <CardContent className="text-center py-12">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto mb-4"></div>
            <p className="text-muted-foreground">Loading your groups...</p>
          </CardContent>
        </Card>
      )}

      {/* Groups Grid */}
      {!loading && (
        <div className="grid gap-4 md:gap-6">
          {filteredGroups.map((group) => (
            <Card key={group.id} className="">
              <CardHeader>
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <CardTitle className="text-lg">{group.name}</CardTitle>
                      <Badge variant="default">Active</Badge>
                    </div>
                  </div>

                  {/* --- THIS IS THE SIMPLIFIED DROPDOWN --- */}
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="ghost" size="icon">
                        <MoreVertical className="h-4 w-4" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem
                        className="text-red-600 focus:text-red-600"
                        onClick={() => {
                          setGroupToDelete(group);
                          setDeleteAlertOpen(true);
                        }}
                      >
                        <Trash className="h-4 w-4 mr-2" />
                        Delete Group
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                  {/* --- END OF SIMPLIFIED DROPDOWN --- */}

                </div>
              </CardHeader>

              <CardContent>
                {/* Members */}
                <div className="flex items-center gap-2 mb-4">
                  <Users className="h-4 w-4 text-muted-foreground" />
                  <div className="flex items-center gap-1">
                    <Avatar className="h-6 w-6 border-2 border-background">
                      <AvatarFallback className="text-xs">You</AvatarFallback>
                    </Avatar>
                    <span className="text-sm text-muted-foreground ml-2">
                      {group.members?.length || 1} member{(group.members?.length || 1) > 1 ? 's' : ''}
                    </span>
                  </div>
                </div>

                {/* Stats */}
                <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-4">
                  <div className="flex items-center gap-2">
                    <DollarSign className="h-4 w-4 text-muted-foreground" />
                    <div>
                      <p className="text-sm text-muted-foreground">Total Expenses</p>
                      <p className="font-medium">${(group.total_expenses || 0).toFixed(2)}</p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <div className="h-2 w-2 rounded-full bg-gray-500" />
                    <div>
                      <p className="text-sm text-muted-foreground">Your Balance</p>
                      <p className="font-medium text-muted-foreground">All settled up</p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 col-span-2 md:col-span-1">
                    <Calendar className="h-4 w-4 text-muted-foreground" />
                    <div>
                      <p className="text-sm text-muted-foreground">Created</p>
                      <p className="font-medium">{new Date(group.created_at).toLocaleDateString()}</p>
                    </div>
                  </div>
                </div>

                {/* Actions */}
                <div className="flex gap-2 pt-2">
                  <Button asChild className="flex-1">
                    <Link to={`/groups/${group.id}`}>
                      View Details
                    </Link>
                  </Button>
                  <Button variant="outline" asChild>
                    <Link to={`/add-expense?group=${group.id}`}>
                      <Plus className="h-4 w-4 mr-2" />
                      Add Expense
                    </Link>
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Empty State */}
      {!loading && filteredGroups.length === 0 && (
        <Card>
          <CardContent className="text-center py-12">
            <Users className="h-12 w-12 mx-auto mb-4 text-muted-foreground opacity-50" />
            <h3 className="text-lg font-medium mb-2">
              {searchTerm ? 'No groups found' : 'No groups yet'}
            </h3>
            <p className="text-muted-foreground mb-4">
              {searchTerm
                ? `No groups match "${searchTerm}". Try a different search term.`
                : 'Create your first group to start splitting expenses with friends and family.'
              }
            </p>
            {!searchTerm && (
              <Button onClick={() => setIsCreateDialogOpen(true)}>
                <Plus className="h-4 w-4 mr-2" />
                Create Your First Group
              </Button>
            )}
          </CardContent>
        </Card>
      )}

      {/* Delete Confirmation Dialog */}
      <AlertDialog
        open={deleteAlertOpen}
        onOpenChange={(open) => {
          setDeleteAlertOpen(open);
          if (!open) {
            setGroupToDelete(null); // Reset on close
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Are you absolutely sure?</AlertDialogTitle>
            <AlertDialogDescription>
              This action cannot be undone. This will permanently delete the
              <strong className="mx-1">{groupToDelete?.name}</strong>
              group and all of its associated expenses.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <Button
              variant="destructive"
              onClick={handleDeleteGroup}
            >
              Delete
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

    </div>
  );
}